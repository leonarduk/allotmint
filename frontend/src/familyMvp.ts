import type { TabsConfig } from './ConfigContext';
import { isModeEnabled } from './pageManifest';
import type { Mode } from './modes';

/**
 * Routes that are permitted in the Family MVP experience.
 *   'owner'        — portfolio view (/portfolio/:owner)
 *   'transactions' — transaction history / input screen (/transactions)
 *
 * All other modes are redirected to the configured MVP entry path when
 * familyMvpEnabled is true. 'performance' was deliberately removed from
 * this set in #2725 — it is a non-MVP route.
 */
export const FAMILY_MVP_MODES: ReadonlySet<Mode> = new Set<Mode>([
  'transactions',
  'owner',
]);

/**
 * Ordered list of entry-path candidates for the Family MVP experience.
 * The first enabled candidate wins (see getFamilyMvpEntryPath).
 *
 * Note: the default entryPath parameter in getFamilyMvpRedirectPath is
 * '/portfolio', but at runtime familyMvpEntryPath is always computed from
 * this list and passed explicitly — so in practice the entry point resolves
 * to whichever of these candidates is enabled first (typically /transactions
 * once that tab is enabled, or /portfolio via the 'owner' mode).
 */
const FAMILY_MVP_ENTRY_CANDIDATES = [
  // Owner mode is routed under /portfolio paths.
  { mode: 'owner', path: '/portfolio' },
  { mode: 'performance', path: '/performance' },
  { mode: 'transactions', path: '/transactions' },
] as const;

export function isFamilyMvpMode(mode: Mode): boolean {
  return FAMILY_MVP_MODES.has(mode);
}

export function getFamilyMvpEntryPath(
  tabs: TabsConfig,
  disabledTabs?: readonly string[]
): string | null {
  for (const candidate of FAMILY_MVP_ENTRY_CANDIDATES) {
    if (isModeEnabled(candidate.mode, tabs, disabledTabs)) {
      return candidate.path;
    }
  }
  return null;
}
