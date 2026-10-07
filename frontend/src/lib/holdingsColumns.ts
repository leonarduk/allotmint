// Column visibility model for HoldingsTable: Simple/Detailed presets and the
// saved per-column choice (#7832).

export const COLUMN_VISIBILITY_STORAGE_KEY = 'holdingsTableColumns';

// Toggleable columns, in table order. "Detailed" is the full set.
export const DETAILED_COLUMNS = {
  sector: true,
  units: true,
  market: true,
  gain: true,
  gain_pct: true,
  total_return: true,
  price: true,
  cost: true,
  weight_pct: true,
  trend: true,
  ccy: true,
  type: true,
  acquired: true,
  days_held: true,
  stage: true,
  eligible: true,
};
export type ColumnKey = keyof typeof DETAILED_COLUMNS;
export type ColumnVisibility = Record<ColumnKey, boolean>;

// "Simple" (ticker, name, units, market value, gain) fits without horizontal
// scrolling and is the default for anyone without a saved choice (#7832).
export const SIMPLE_COLUMNS: ColumnVisibility = {
  ...(Object.fromEntries(
    Object.keys(DETAILED_COLUMNS).map((key) => [key, false])
  ) as ColumnVisibility),
  units: true,
  market: true,
  gain: true,
};

export const COLUMN_PRESETS = {
  simple: SIMPLE_COLUMNS,
  detailed: DETAILED_COLUMNS,
};
export type ColumnPreset = keyof typeof COLUMN_PRESETS;

// Money columns that relative view hides regardless of visibleColumns.
export const RELATIVE_VIEW_HIDDEN: ReadonlySet<ColumnKey> = new Set([
  'units',
  'market',
  'gain',
  'total_return',
  'cost',
]);
// The columns after weight %; group and total rows render a filler cell for each.
export const TRAILING_COLUMNS: ColumnKey[] = [
  'trend',
  'ccy',
  'type',
  'acquired',
  'days_held',
  'stage',
  'eligible',
];

// A saved choice overrides the Simple default key by key, so a column added
// later starts hidden rather than discarding the rest of the saved choice.
export function loadColumnVisibility(): ColumnVisibility {
  if (typeof window === 'undefined') return { ...SIMPLE_COLUMNS };
  try {
    const stored = JSON.parse(
      localStorage.getItem(COLUMN_VISIBILITY_STORAGE_KEY) ?? 'null'
    ) as Partial<Record<string, unknown>> | null;
    if (!stored || typeof stored !== 'object') return { ...SIMPLE_COLUMNS };
    const visibility = { ...SIMPLE_COLUMNS };
    for (const key of Object.keys(visibility) as ColumnKey[]) {
      if (typeof stored[key] === 'boolean') visibility[key] = stored[key];
    }
    return visibility;
  } catch (error) {
    console.warn('Ignoring unreadable holdings column preferences', error);
    return { ...SIMPLE_COLUMNS };
  }
}

export function matchingPreset(
  visibility: ColumnVisibility
): ColumnPreset | null {
  const presets = Object.keys(COLUMN_PRESETS) as ColumnPreset[];
  return (
    presets.find((preset) =>
      (Object.keys(visibility) as ColumnKey[]).every(
        (key) => COLUMN_PRESETS[preset][key] === visibility[key]
      )
    ) ?? null
  );
}
