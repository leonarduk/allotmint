"""Cash deployment tracker (#10480).

The owner records a schedule for phasing a cash balance into their plan; this
package works out each tranche's split (via
:func:`backend.common.rebalance_plan.suggest_new_cash`), drafts an order list
from the plan's own ``vehicles``, and checks the account's BUY transactions to
see whether each tranche was carried out. Nothing here places trades or
proposes a schedule.
"""
