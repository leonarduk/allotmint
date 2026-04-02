import type { TabsConfig } from './ConfigContext';
import type { Mode } from './modes';
import { isModeEnabled } from './pageManifest';

export const FAMILY_MVP_MODES: ReadonlySet<Mode> = new Set<Mode>([
  'transactions',
  'owner',
  'performance',
]);

export function isFamilyMvpMode(mode: Mode): boolean {
  return FAMILY_MVP_MODES.has(mode);
}

export function getFamilyMvpEntryPath(
  tabs: TabsConfig,
  disabledTabs?: readonly string[]
): string | null {
  if (isModeEnabled('owner', tabs, disabledTabs)) return '/portfolio';
  if (isModeEnabled('performance', tabs, disabledTabs)) return '/performance';
  if (isModeEnabled('transactions', tabs, disabledTabs)) return '/transactions';
  return null;
}
