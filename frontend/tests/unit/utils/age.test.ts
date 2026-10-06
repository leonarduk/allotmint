import { describe, expect, it } from 'vitest';
import { ageInWholeYears } from '@/utils/age';

describe('ageInWholeYears', () => {
  const dob = '2013-03-11';

  it('does not round up past the half-year mark', () => {
    expect(ageInWholeYears(dob, new Date(2026, 9, 6))).toBe(13);
  });

  it('is one year younger the day before the birthday', () => {
    expect(ageInWholeYears(dob, new Date(2026, 2, 10))).toBe(12);
  });

  it('ticks over on the birthday itself', () => {
    // days / 365.25 gives 12.999 here, which is why the fractional age
    // from the API can't simply be floored.
    expect(ageInWholeYears(dob, new Date(2026, 2, 11))).toBe(13);
  });

  it('returns null for missing or malformed input', () => {
    expect(ageInWholeYears(null)).toBeNull();
    expect(ageInWholeYears('')).toBeNull();
    expect(ageInWholeYears('11/03/2013')).toBeNull();
    expect(ageInWholeYears('2013-13-45')).toBeNull();
    expect(ageInWholeYears('2013-02-30')).toBeNull();
  });
});
