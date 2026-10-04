// UK pension reference figures used to seed and bound the Pension Forecast
// form. They change every April, so keep them together and update them here.

export const UK_PENSION_FIGURES_TAX_YEAR = "2026/27";

/**
 * Pension annual allowance: the most that can be paid into pensions in a tax
 * year with tax relief -- your contributions (including tax relief) and your
 * employer's combined. It can be lower (tapered allowance for very high
 * earners, or the £10,000 money purchase annual allowance once a pension has
 * been flexibly accessed), which the form mentions but doesn't model.
 */
export const PENSION_ANNUAL_ALLOWANCE_GBP = 60_000;
export const PENSION_MONTHLY_ALLOWANCE_GBP = PENSION_ANNUAL_ALLOWANCE_GBP / 12;

/** Full new State Pension for 2026/27: £241.30 a week (35 qualifying NI years). */
export const FULL_NEW_STATE_PENSION_WEEKLY_GBP = 241.3;
export const FULL_NEW_STATE_PENSION_ANNUAL_GBP = 12_548;

export type Household = "single" | "couple";
export type LivingStandard = "minimum" | "moderate" | "comfortable";

/**
 * Pensions UK Retirement Living Standards, 2026/27 (as published by Which?):
 * annual spending after tax, assuming the home is owned outright (no rent or
 * mortgage).
 */
export const RETIREMENT_LIVING_STANDARDS_ANNUAL_GBP: Record<
  Household,
  Record<LivingStandard, number>
> = {
  single: { minimum: 13_900, moderate: 32_700, comfortable: 45_400 },
  couple: { minimum: 22_500, moderate: 45_400, comfortable: 62_700 },
};

export const LIVING_STANDARDS: LivingStandard[] = [
  "minimum",
  "moderate",
  "comfortable",
];

/** Monthly equivalent, rounded to the nearest £10 so it lands on the slider's step. */
export const livingStandardMonthly = (
  household: Household,
  standard: LivingStandard,
) =>
  Math.round(RETIREMENT_LIVING_STANDARDS_ANNUAL_GBP[household][standard] / 120) *
  10;
