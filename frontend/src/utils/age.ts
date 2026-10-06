/**
 * Calendar age in whole years for an ISO ``YYYY-MM-DD`` date of birth.
 *
 * The backend reports age as ``days / 365.25``, which is fine for forecast
 * maths but can't be rounded or floored into a displayed age reliably:
 * rounding overstates age for half the year, and flooring can be a day late
 * on the birthday itself. Returns ``null`` for missing or malformed input.
 */
export function ageInWholeYears(
  dob: string | null | undefined,
  today: Date = new Date()
): number | null {
  const match = dob ? /^(\d{4})-(\d{2})-(\d{2})$/.exec(dob) : null;
  if (!match) return null;
  const [year, month, day] = match.slice(1).map(Number);
  // Reject impossible dates such as 2013-02-30 (Date would roll them over).
  const parsed = new Date(year, month - 1, day);
  if (parsed.getMonth() !== month - 1 || parsed.getDate() !== day) return null;
  // Local calendar date on purpose: age ticks over at the viewer's midnight.
  const hadBirthdayThisYear =
    today.getMonth() + 1 > month ||
    (today.getMonth() + 1 === month && today.getDate() >= day);
  return today.getFullYear() - year - (hadBirthdayThisYear ? 0 : 1);
}
