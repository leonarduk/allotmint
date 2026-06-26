import type { TabsConfig } from './ConfigContext';
import { isModeEnabled } from './pageManifest';

/**
 * Family MVP affects exactly one thing: the default landing page.
 *
 * It does NOT restrict which routes a user may reach. Any tab that is enabled
 * in config is fully navigable; route reachability is governed solely by the
 * tab gating in App.tsx (isModeEnabled / tabs / disabledTabs). The previous
 * FAMILY_MVP_MODES allowlist + isFamilyMvpMode redirect guard were removed in
 * #4641 because they silently bounced enabled tabs (search, settings, …) back
 * to the entry path.
 *
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
  { mode: 'transactions', path: '/input' },
  // Owner mode is routed under /portfolio paths.
  { mode: 'owner', path: '/portfolio' },
  { mode: 'performance', path: '/performance' },
] as const;

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
