import { useAuth } from "../AuthContext";

/**
 * Default explanation surfaced on a disabled mutating control while
 * `demoReadOnly` is set. Callers may pass a more specific reason to
 * `useDemoReadOnly().reason(...)` when the generic wording isn't clear
 * enough for the surface (e.g. naming the specific action).
 */
export const DEMO_READONLY_MESSAGE =
  "Not available in the read-only demo — sign in to make changes.";

/**
 * Shared read for the `demoReadOnly` flag (issue #7410) that mutating UI
 * controls consume to hide/disable themselves (issue #7411).
 *
 * This is a UX courtesy only, not an authorization boundary: the
 * server-side gates (#7407, #7408) are what actually enforce read-only
 * access for a demo-scoped token. A control that skips this hook and stays
 * enabled will still be rejected with a 403 by the server — this hook only
 * prevents a demo visitor from seeing a control that is guaranteed to fail.
 *
 * Usage: disable a control with `disabled={busy || demoReadOnly}` and pair
 * it with a `title`/`aria-label` built from `reason()` so the disabled
 * state explains itself instead of reading as a bug.
 */
export function useDemoReadOnly(): {
  demoReadOnly: boolean;
  reason: (message?: string) => string | undefined;
} {
  const { demoReadOnly } = useAuth();
  const reason = (message: string = DEMO_READONLY_MESSAGE) =>
    demoReadOnly ? message : undefined;
  return { demoReadOnly, reason };
}
