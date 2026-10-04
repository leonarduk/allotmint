/**
 * Shared helpers for turning raw backend forecast/calculation errors into
 * plain-language messages suitable for display to end users.
 *
 * Extracted from `PensionForecast.tsx` (originally added in PR #7134) so
 * other forecast/calculation pages can reuse the same mapping and
 * 4xx-vs-5xx handling without duplicating the logic.
 */

export type ForecastErrorContext = {
  /** The death age (a.k.a. "plan until age") the user submitted. */
  deathAge: number;
  /**
   * The retirement age, if it is already known (e.g. from a prior forecast
   * response). When `null`, the message omits the specific age.
   */
  retirementAge: number | null;
  /** HTTP status code from the failed request, if available. */
  status?: number;
};

/**
 * Map a raw backend error message into a user-facing string.
 *
 * Behaviour:
 * - Known backend detail strings (e.g. `"death_age must exceed
 *   retirement_age"`, `"missing or invalid dob"`) are mapped to
 *   plain-language copy, using `context` to fill in specifics like the
 *   submitted death age and the known retirement age.
 * - Unrecognised 4xx errors are described as an input problem, since the
 *   request itself was rejected as invalid.
 * - Everything else (5xx, timeouts, network failures) is passed through
 *   unchanged: `api.ts` has already turned those into readable copy, and
 *   telling the user to "check your inputs" when the backend is down would
 *   send them to fix something that isn't broken.
 * - The raw message is trimmed before lookup so whitespace differences
 *   don't defeat the known-message map.
 *
 * @param rawMessage The raw error message from the API layer.
 * @param context    Context used to build the humanised message.
 * @returns A user-facing error string.
 */
export function humanizeForecastError(
  rawMessage: string,
  context: ForecastErrorContext,
): string {
  const knownDetailMessages: Record<
    string,
    (ctx: ForecastErrorContext) => string
  > = {
    "death_age must exceed retirement_age": (ctx) =>
      ctx.retirementAge != null
        ? `Death age (${ctx.deathAge}) must be after your retirement age (${ctx.retirementAge}).`
        : `Death age (${ctx.deathAge}) must be after your retirement age.`,
    "retirement_age must not be before current_age": (ctx) =>
      ctx.retirementAge != null
        ? `Retirement age (${ctx.retirementAge}) can't be earlier than your current age.`
        : "Retirement age can't be earlier than your current age.",
    "missing or invalid dob": () =>
      "We couldn't determine this owner's date of birth. Please check their profile details and try again.",
  };

  const handler = knownDetailMessages[rawMessage.trim()];
  if (handler) return handler(context);

  // Only an unrecognised *client* error is safely described as an input
  // problem. Everything else -- a 5xx, a timeout, a network failure -- is
  // not the user's inputs, and api.ts has already turned those into
  // readable copy ("The backend service is temporarily unavailable...",
  // the timeout message). Telling the user to "check your inputs" when the
  // backend is down sends them to fix something that isn't broken, so pass
  // the message through instead.
  const status = context.status;
  if (status != null && status >= 400 && status < 500) {
    return "We couldn't calculate this forecast. Please check your inputs and try again.";
  }
  return (
    rawMessage.trim() ||
    "We couldn't calculate this forecast. Please try again."
  );
}
