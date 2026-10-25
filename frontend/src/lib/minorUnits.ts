/**
 * Parse a £ amount typed by the owner into integer pence without going through
 * floating point (so "0.30" is exactly 30, never 29.999…). Returns null for
 * anything that is not a positive amount with at most two decimal places.
 */
export function poundsToMinor(input: string): number | null {
  const match = /^£?\s*(\d+)(?:\.(\d{1,2}))?$/.exec(input.trim().replace(/,/g, ""));
  if (!match) return null;
  const minor = Number(match[1]) * 100 + Number((match[2] ?? "").padEnd(2, "0"));
  return minor > 0 && Number.isSafeInteger(minor) ? minor : null;
}

/** Integer pence to a plain "12.34" string for a £ input. */
export function minorToPounds(minor: number): string {
  return `${Math.floor(minor / 100)}.${String(minor % 100).padStart(2, "0")}`;
}
