import { describe, expect, it } from 'vitest';
import {
  humanizeForecastError,
  type ForecastErrorContext,
} from '@/utils/forecastErrors';

// Table of every backend detail string `humanizeForecastError` maps (#8309),
// so a dropped or reworded mapping fails here without a page render. The
// strings mirror backend/routes/pension.py's HTTPException details.
const KNOWN_DETAIL_CASES: Array<{
  raw: string;
  context: ForecastErrorContext;
  expected: string;
}> = [
  {
    raw: 'death_age must exceed retirement_age',
    context: { deathAge: 50, retirementAge: 67 },
    expected: 'Death age (50) must be after your retirement age (67).',
  },
  {
    raw: 'death_age must exceed retirement_age',
    context: { deathAge: 50, retirementAge: null },
    expected: 'Death age (50) must be after your retirement age.',
  },
  {
    raw: 'retirement_age must not be before current_age',
    context: { deathAge: 90, retirementAge: 30 },
    expected: "Retirement age (30) can't be earlier than your current age.",
  },
  {
    raw: 'retirement_age must not be before current_age',
    context: { deathAge: 90, retirementAge: null },
    expected: "Retirement age can't be earlier than your current age.",
  },
  {
    raw: 'missing or invalid dob',
    context: { deathAge: 90, retirementAge: null },
    expected:
      "We couldn't determine this owner's date of birth. Please check their profile details and try again.",
  },
];

describe('humanizeForecastError known backend details', () => {
  it.each(KNOWN_DETAIL_CASES)(
    'maps $raw (retirementAge=$context.retirementAge)',
    ({ raw, context, expected }) => {
      expect(humanizeForecastError(raw, context)).toBe(expected);
    }
  );

  it.each(KNOWN_DETAIL_CASES)(
    'maps $raw even when the backend returns it with a 400 status',
    ({ raw, context, expected }) => {
      // A known detail must win over the generic "check your inputs" copy
      // that an unrecognised 4xx falls back to.
      expect(humanizeForecastError(raw, { ...context, status: 400 })).toBe(
        expected
      );
    }
  );
});
