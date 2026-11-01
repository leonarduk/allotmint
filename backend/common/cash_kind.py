"""Structured ``kind`` for cash transactions (#10797).

``Transaction.kind`` says what a cash movement *is* -- a pension contribution,
a relief-at-source top-up, a transfer in, an ISA subscription -- so readers do
not have to guess it from comment text. The closed vocabulary is
:data:`CASH_KINDS`. ``kind`` stays optional: a null ``kind`` means "not
classified" and every reader falls back to its existing comment rules.

:func:`classify_cash_kind` sets a kind only for unambiguous rows and returns
``None`` for everything else; it never guesses. It is used when rows are
imported (``POST /transactions/import``) and by the one-off backfill
``scripts/backfill_transaction_kind.py``. It never replaces a ``kind`` that is
already set, including the legacy ``"account"`` the Moneyhub API importer
writes (an account-level cash row, not a cash classification).

Rules, by ``type`` and account (comments are matched case-insensitively):

- ``WITHDRAWAL`` -> ``withdrawal``; ``INTEREST`` -> ``interest``;
  ``FEES``/``FEE`` -> ``fee`` (the type already says so).
- ``TRANSFER_IN`` with no ticker (cash, not an in-specie transfer) ->
  ``isa_transfer_in`` on an ISA account, otherwise ``transfer_in``.
- ``DEPOSIT`` into an ISA account -> ``isa_transfer_in`` when the comment says
  "transfer(red) in" or "ISA transfer"; ``isa_subscription`` when the comment
  mentions none of transfer, refund, reversal, repayment, correction,
  interest, bonus, relief or cashback (a blank comment is a subscription, as
  the allowance guardian already assumes). Anything else is left unclassified.
- Positive ``DEPOSIT`` into a pension (SIPP) account, unless the comment
  mentions a refund, reversal, repayment or correction:
  ``transfer_in`` for "transfer(red) in" with no contribution, relief or
  employer wording; ``tax_relief`` for "tax relief"/"relief at source" with no
  employer or transfer wording; ``employer_contribution`` for an employer or
  salary-sacrifice tag with no relief or transfer wording; and
  ``personal_contribution`` for "contribution" with none of those. Any other
  comment (including a blank one, "Transfer of contribution", or mixed
  wording) is left unclassified.
- Everything else (deposits into other accounts, dividends, trades) is left
  unclassified.
"""

from __future__ import annotations

import re
from typing import Any, Mapping, Optional

from backend.common.pension import DEFINED_CONTRIBUTION_ACCOUNT_MARKERS

# Whole-word comment tags marking an employer or salary-sacrifice DEPOSIT. Mirrors
# allotmint_pro.mcp_server.transaction_summary.EMPLOYER_COMMENT_TAGS, which decides
# what counts towards the annual allowance. Also used by the allowance guardian's
# contribution matching (backend.allowance_guardian.match).
EMPLOYER_COMMENT_TAGS = ("employer", "salary sacrifice", "salary exchange")

PERSONAL_CONTRIBUTION = "personal_contribution"
TAX_RELIEF = "tax_relief"
EMPLOYER_CONTRIBUTION = "employer_contribution"
TRANSFER_IN = "transfer_in"
ISA_SUBSCRIPTION = "isa_subscription"
ISA_TRANSFER_IN = "isa_transfer_in"
WITHDRAWAL = "withdrawal"
INTEREST = "interest"
FEE = "fee"

CASH_KINDS = frozenset(
    {
        PERSONAL_CONTRIBUTION,
        TAX_RELIEF,
        EMPLOYER_CONTRIBUTION,
        TRANSFER_IN,
        ISA_SUBSCRIPTION,
        ISA_TRANSFER_IN,
        WITHDRAWAL,
        INTEREST,
        FEE,
    }
)

# Types whose kind follows from the type alone.
_KIND_BY_TYPE = {"WITHDRAWAL": WITHDRAWAL, "INTEREST": INTEREST, "FEES": FEE, "FEE": FEE}
# Types that are cash movements a kind could describe; the backfill lists the
# ones it leaves unclassified.
CASH_TYPES = frozenset({"DEPOSIT", "TRANSFER_IN", *_KIND_BY_TYPE})

_TRANSFER_IN_RE = re.compile(r"\btransfer(?:red)?\s+in\b")
_ISA_TRANSFER_RE = re.compile(r"\btransfer(?:red)?\s+in\b|\bisa\s+transfer\b")
_ISA_NOT_SUBSCRIPTION_RE = re.compile(r"transfer|refund|revers|repay|correction|interest|bonus|relief|cashback")
_REVERSAL_RE = re.compile(r"refund|revers|repay|correction")
_RELIEF_RE = re.compile(r"tax relief|relief at source")
_EMPLOYER_RE = re.compile(r"\b(?:" + "|".join(EMPLOYER_COMMENT_TAGS) + r")\b")


def is_isa_account(account: str) -> bool:
    """True for an ISA account (any name containing ``isa``, so ``lisa`` too)."""
    return "isa" in (account or "").lower()


def is_pension_account(account: str) -> bool:
    """True for a defined-contribution pension account (e.g. ``sipp``, ``kz:sipp``)."""
    name = (account or "").lower()
    return any(marker in name for marker in DEFINED_CONTRIBUTION_ACCOUNT_MARKERS)


def _isa_deposit_kind(comment: str) -> Optional[str]:
    if _ISA_TRANSFER_RE.search(comment):
        return ISA_TRANSFER_IN
    if _ISA_NOT_SUBSCRIPTION_RE.search(comment):
        return None
    return ISA_SUBSCRIPTION


def _pension_deposit_kind(comment: str) -> Optional[str]:
    if _REVERSAL_RE.search(comment):
        return None
    transfer = "transfer" in comment
    relief = bool(_RELIEF_RE.search(comment))
    employer = bool(_EMPLOYER_RE.search(comment))
    contribution = "contribution" in comment
    if transfer:
        if _TRANSFER_IN_RE.search(comment) and not (relief or employer or contribution):
            return TRANSFER_IN
        return None
    if relief:
        return None if employer else TAX_RELIEF
    if employer:
        return EMPLOYER_CONTRIBUTION
    return PERSONAL_CONTRIBUTION if contribution else None


def _float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def classify_cash_kind(row: Mapping[str, Any], account: str) -> Optional[str]:
    """Return the cash ``kind`` for a transaction ``row`` in ``account``, or ``None`` when unsure.

    ``row`` is a stored transaction dict (``type``, ``ticker``, ``comments``,
    ``amount_minor``). Does not look at an existing ``kind``; callers keep a
    non-null one. See the module docstring for the rules.
    """
    tx_type = str(row.get("type") or "").strip().upper()
    if tx_type in _KIND_BY_TYPE:
        return _KIND_BY_TYPE[tx_type]
    isa = is_isa_account(account)
    if tx_type == "TRANSFER_IN":
        if row.get("ticker"):
            return None
        return ISA_TRANSFER_IN if isa else TRANSFER_IN
    if tx_type != "DEPOSIT":
        return None
    comment = str(row.get("comments") or "").lower()
    if isa:
        return _isa_deposit_kind(comment)
    amount = _float(row.get("amount_minor"))
    if is_pension_account(account) and amount is not None and amount > 0:
        return _pension_deposit_kind(comment)
    return None
