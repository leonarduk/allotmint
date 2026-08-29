/**
 * Central place for turning a raw `account_type` slug (e.g. "isa", "sipp") into
 * a human-readable label, and for classifying which account types actually
 * count toward the pension forecast calculation.
 *
 * `account_type` values coming from the backend (see the per-account JSON
 * files under `data/accounts/`) are lowercase internal slugs, not display
 * text -- see issue #7211, where the Pension Forecast page was rendering
 * `isa` / `sipp` verbatim instead of "ISA" / "SIPP". Anywhere the UI needs
 * to show an account type to a user it should go through this module rather
 * than rendering the raw slug or inventing another mapping.
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
 * Lower-case substrings that mark an account_type as counting toward the
 * defined-contribution pension pot / forecast calculation.
 *
 * This MUST mirror `DEFINED_CONTRIBUTION_ACCOUNT_MARKERS` in
 * `backend/common/pension.py` exactly, including the substring (not exact)
 * match -- that constant is what `dc_pension_pot_gbp` actually uses to
 * compute `pension_pot_gbp` for a real forecast. If this list drifts from
 * the backend's, the frontend's seeded "Current pension pot" figure (see
 * PensionForecast.tsx) and the "used in this forecast" grouping can show
 * numbers/accounts that don't match what a real forecast run returns --
 * this is exactly the kind of mismatch a #7211 follow-up review caught:
 * an account_type of "pension" (not "sipp") is NOT counted by the backend,
 * and "workplace-sipp" / "kz:sipp" (containing "sipp") ARE counted, so an
 * exact-match set here would be wrong in both directions.
 */
const DEFINED_CONTRIBUTION_ACCOUNT_MARKERS = ["sipp"];

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

/**
 * Whether an account_type counts toward the pension forecast calculation --
 * i.e. whether the backend's `dc_pension_pot_gbp` would include it. This is
 * a narrower question than "is this conceptually a pension account": an
 * account_type of exactly "pension" does NOT match (the backend only
 * recognises "sipp"-family substrings today), so this function is
 * deliberately named around what it actually decides rather than implying a
 * broader classification it doesn't make.
 */
export function countsTowardPensionForecast(accountType: string): boolean {
  const key = accountType.trim().toLowerCase();
  return DEFINED_CONTRIBUTION_ACCOUNT_MARKERS.some((marker) => key.includes(marker));
}
