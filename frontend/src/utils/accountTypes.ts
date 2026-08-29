/**
 * Central place for turning a raw `account_type` slug (e.g. "isa", "sipp") into
 * a human-readable label, and for classifying which account types are pension
 * wrappers.
 *
 * `account_type` values coming from the backend (see the per-account JSON
 * files under `data/accounts/`)
 * are lowercase internal slugs, not display text -- see issue #7211, where the
 * Pension Forecast page was rendering `isa` / `sipp` verbatim instead of
 * "ISA" / "SIPP". Anywhere the UI needs to show an account type to a user it
 * should go through this module rather than rendering the raw slug or
 * inventing another mapping.
 *
 * The known account types mirror `gamified/plotModel.ts`'s `BED_ICONS` map,
 * which is the other place account types are enumerated in the frontend --
 * kept in sync deliberately so a type added there also gets a sensible label
 * here.
 */
const ACCOUNT_TYPE_LABELS: Record<string, string> = {
  isa: "ISA",
  "stocks-isa": "Stocks & Shares ISA",
  sipp: "SIPP",
  pension: "Pension",
  gia: "GIA",
  general: "General",
  ltd: "Ltd company",
  jisa: "JISA",
  lisa: "LISA",
  cash: "Cash",
  savings: "Savings",
};

/**
 * account_type slugs that are pension wrappers -- i.e. subject to pension
 * access rules (a minimum pension age) rather than being freely accessible
 * like an ISA or GIA. Deliberately not assumed to be just {isa, sipp}: any
 * future pension-style wrapper should be added here explicitly (#7211).
 */
const PENSION_ACCOUNT_TYPES = new Set(["sipp", "pension"]);

/** Render a raw account_type slug as a human label, e.g. "isa" -> "ISA". */
export function accountTypeLabel(accountType: string): string {
  const key = accountType.trim().toLowerCase();
  const known = ACCOUNT_TYPE_LABELS[key];
  if (known) return known;

  // Unknown account type: fall back to a title-cased version of the slug
  // rather than the raw lowercase string, so it still reads as a label.
  return key
    .split(/[-_\s]+/)
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

/** Whether an account_type slug is a pension wrapper (SIPP, etc). */
export function isPensionAccountType(accountType: string): boolean {
  return PENSION_ACCOUNT_TYPES.has(accountType.trim().toLowerCase());
}
