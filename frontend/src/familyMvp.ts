import type { TabsConfig } from './ConfigContext';
import { isModeEnabled } from './pageManifest';
import type { Mode } from './modes';

export const FAMILY_MVP_MODES: ReadonlySet<Mode> = new Set<Mode>([
  'transactions',
  'owner',
  'performance',
]);

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
