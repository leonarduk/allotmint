import type { Mode } from './modes';

export const FAMILY_MVP_MODES: ReadonlySet<Mode> = new Set<Mode>([
  'transactions',
  'owner',
]);

export function isFamilyMvpMode(mode: Mode): boolean {
  return FAMILY_MVP_MODES.has(mode);
}
