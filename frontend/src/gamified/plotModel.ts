/**
 * Pure domain mapping for Plot mode (the gamified skin).
 *
 * Everything in here is deliberately free of React and network access so the
 * "does a 42% gain really make this a flowering crop?" rules can be unit
 * tested on their own. Screens call `buildPlotSnapshot` once and render the
 * result; no game state is invented here — every number traces back to a real
 * portfolio, trail or allowance figure from the API.
 */

import type { Account, Holding, Portfolio } from '../types';

export type GrowthStage =
  | 'wilting'
  | 'seed'
  | 'sprout'
  | 'leafing'
  | 'budding'
  | 'flowering'
  | 'fruiting'
  | 'bumper';

export interface GrowthStageMeta {
  id: GrowthStage;
  label: string;
  icon: string;
  /** Hex accent used for the stage chip and the crop card's aura. */
  accent: string;
}

/** Ordered worst → best so progress bars and sorts can use the index. */
export const GROWTH_STAGES: readonly GrowthStageMeta[] = [
  { id: 'wilting', label: 'Wilting', icon: '🥀', accent: '#e2643f' },
  { id: 'seed', label: 'Sown', icon: '🌰', accent: '#a98363' },
  { id: 'sprout', label: 'Sprouting', icon: '🌱', accent: '#8fd694' },
  { id: 'leafing', label: 'Leafing', icon: '🍃', accent: '#63d19e' },
  { id: 'budding', label: 'Budding', icon: '🌿', accent: '#4fd1c5' },
  { id: 'flowering', label: 'Flowering', icon: '🌸', accent: '#7cc0ff' },
  { id: 'fruiting', label: 'Fruiting', icon: '🍅', accent: '#f2a33c' },
  { id: 'bumper', label: 'Bumper crop', icon: '🏆', accent: '#f2c14e' },
];

const STAGE_BY_ID = new Map(GROWTH_STAGES.map((stage) => [stage.id, stage]));

/**
 * The crop detail screen's "Yield" trait level (0–5) for a growth stage.
 *
 * Derived from the stage rather than re-thresholded off `gain_pct`: the two
 * ladders previously disagreed at every boundary (`growthStageFor` bands with
 * `<=`, so a crop on exactly 120% is fruiting — a second ladder using `>=`
 * called the same crop bumper), which showed as a chip and a trait level that
 * contradicted each other.
 */
const STAGE_LEVELS: Record<GrowthStage, number> = {
  wilting: 0,
  seed: 0,
  sprout: 1,
  leafing: 1,
  budding: 2,
  flowering: 3,
  fruiting: 4,
  bumper: 5,
};

export function growthLevelFor(stage: GrowthStage): number {
  return STAGE_LEVELS[stage] ?? 0;
}

export function growthStageMeta(stage: GrowthStage): GrowthStageMeta {
  // STAGE_BY_ID covers the whole union, but a defensive fallback keeps a
  // malformed persisted value from crashing a render.
  return STAGE_BY_ID.get(stage) ?? GROWTH_STAGES[1];
}

/**
 * Total gain % decides how far a crop has grown. Thresholds are deliberately
 * generous at the low end so a freshly bought holding shows visible progress
 * rather than sitting at "sown" for months.
 */
export function growthStageFor(
  gainPct: number | null | undefined
): GrowthStage {
  const pct = Number.isFinite(gainPct) ? (gainPct as number) : 0;
  if (pct <= -20) return 'wilting';
  if (pct <= 0) return 'seed';
  if (pct <= 5) return 'sprout';
  if (pct <= 15) return 'leafing';
  if (pct <= 30) return 'budding';
  if (pct <= 60) return 'flowering';
  if (pct <= 120) return 'fruiting';
  return 'bumper';
}

/**
 * Star rating (1–7, like the arcade games this skin borrows from) from the
 * crop's share of total plot value: how much of the allotment it occupies.
 */
export function starsFor(shareOfPlot: number): number {
  const share = Number.isFinite(shareOfPlot) ? shareOfPlot : 0;
  if (share >= 0.2) return 7;
  if (share >= 0.12) return 6;
  if (share >= 0.07) return 5;
  if (share >= 0.04) return 4;
  if (share >= 0.02) return 3;
  if (share >= 0.01) return 2;
  return 1;
}

/**
 * Vigour (0–100) is a *freshness and momentum* read, not a performance one:
 * today's move mapped from ±5% onto the full bar, with a penalty when the
 * price feed is stale so neglected crops visibly droop.
 */
export function vigourFor(
  holding: Pick<Holding, 'day_change_gbp' | 'market_value_gbp' | 'is_stale'>
): number {
  const value = holding.market_value_gbp ?? 0;
  const dayChange = holding.day_change_gbp ?? 0;
  const dayPct = value > 0 ? (dayChange / value) * 100 : 0;
  const momentum = 50 + (dayPct / 5) * 50;
  const penalty = holding.is_stale ? 30 : 0;
  return Math.round(clamp(momentum - penalty, 0, 100));
}

export function clamp(value: number, min: number, max: number): number {
  if (!Number.isFinite(value)) return min;
  return Math.min(max, Math.max(min, value));
}

export interface GrowerLevel {
  level: number;
  /** XP earned since this level started. */
  xpIntoLevel: number;
  /** XP required to move from this level to the next. */
  xpForLevel: number;
  xpTotal: number;
  /** 0–100, for the HUD ring and bar. */
  pct: number;
}

/**
 * Cumulative XP needed to *reach* level L is `25 * L * (L - 1)`:
 * L1 at 0 XP, L2 at 50, L3 at 150, L4 at 300 — quick early levels that
 * stretch out, which is what makes a daily-chore loop feel rewarding.
 */
export function xpThresholdForLevel(level: number): number {
  const safe = Math.max(1, Math.floor(level));
  return 25 * safe * (safe - 1);
}

/** Highest level fully paid for by `xp`, plus progress into the next one. */
export function levelFromXp(xp: number | null | undefined): GrowerLevel {
  const total = Number.isFinite(xp) ? Math.max(0, Math.floor(xp as number)) : 0;
  let level = 1;
  // The curve is quadratic, so this loop is O(sqrt(xp)); the cap keeps a
  // corrupt XP value from spinning here.
  while (level < 999 && xpThresholdForLevel(level + 1) <= total) {
    level += 1;
  }
  const base = xpThresholdForLevel(level);
  const next = xpThresholdForLevel(level + 1);
  const xpForLevel = next - base;
  const xpIntoLevel = total - base;
  return {
    level,
    xpIntoLevel,
    xpForLevel,
    xpTotal: total,
    pct: xpForLevel > 0 ? clamp((xpIntoLevel / xpForLevel) * 100, 0, 100) : 0,
  };
}

/** Flavour title shown next to the level, so progress reads as a rank. */
export function growerRank(level: number): string {
  if (level >= 40) return 'Head Gardener';
  if (level >= 25) return 'Master Grower';
  if (level >= 15) return 'Plotholder';
  if (level >= 8) return 'Seasoned Digger';
  if (level >= 4) return 'Weekend Grower';
  return 'Seedling Sower';
}

export interface Crop {
  /**
   * Unique per holding row, not per ticker: the same instrument legitimately
   * appears in several beds AND several times within one bed (the repo's own
   * demo accounts hold VWRL.L twice in a single ISA). Keying React lists or
   * detail routes on `ticker` alone collides on that data.
   */
  id: string;
  ticker: string;
  name: string;
  bedId: string;
  bedName: string;
  units: number;
  valueGbp: number;
  costGbp: number;
  gainGbp: number;
  gainPct: number;
  dayChangePct: number;
  stage: GrowthStage;
  stars: number;
  vigour: number;
  /** Share of total plot value, 0–1. */
  share: number;
  sector: string;
  region: string;
  instrumentType: string;
  stale: boolean;
  lastPriceDate: string | null;
  /** Days held, when the API knows — drives the "ready to lift" hint. */
  daysHeld: number | null;
  sellEligible: boolean;
  /** Days until the minimum holding period is served, when the API knows. */
  daysUntilEligible: number | null;
  nextEligibleSellDate: string | null;
}

/** Account types get a bed identity so the roster can be grouped visually. */
const BED_ICONS: Record<string, string> = {
  isa: '🌻',
  'stocks-isa': '🌻',
  sipp: '🌳',
  pension: '🌳',
  gia: '🥕',
  general: '🥕',
  ltd: '🏡',
  jisa: '🌷',
  lisa: '🪴',
  cash: '🪣',
  savings: '🪣',
};

export function bedIconFor(accountType: string): string {
  const key = accountType.trim().toLowerCase();
  return BED_ICONS[key] ?? '🌱';
}

/** "stocks-isa" → "Stocks Isa"; used as the bed's display name. */
export function bedNameFor(accountType: string): string {
  const cleaned = accountType.replace(/[-_]+/g, ' ').trim();
  if (!cleaned) return 'Unnamed bed';
  return cleaned
    .split(/\s+/)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

export interface Bed {
  id: string;
  name: string;
  icon: string;
  owner: string | null;
  valueGbp: number;
  cropCount: number;
  currency: string;
  lastUpdated: string | null;
}

export function bedFromAccount(account: Account, index: number): Bed {
  const type = account.account_type ?? `bed-${index}`;
  return {
    // Owner is part of the id because a group portfolio can hold the same
    // account type for several people.
    id: `${account.owner ?? 'plot'}:${type}`,
    name: bedNameFor(type),
    icon: bedIconFor(type),
    owner: account.owner ?? null,
    valueGbp: account.value_estimate_gbp ?? 0,
    cropCount: account.holdings?.length ?? 0,
    currency: account.currency ?? 'GBP',
    lastUpdated: account.last_updated ?? null,
  };
}

function cropFromHolding(
  holding: Holding,
  bed: Bed,
  plotValue: number,
  bedIndex: number,
  holdingIndex: number
): Crop {
  const valueGbp = holding.market_value_gbp ?? 0;
  const costGbp =
    holding.effective_cost_basis_gbp ?? holding.cost_basis_gbp ?? 0;
  const gainGbp = holding.gain_gbp ?? valueGbp - costGbp;
  const gainPct =
    holding.gain_pct ?? (costGbp > 0 ? (gainGbp / costGbp) * 100 : 0);
  const share = plotValue > 0 ? valueGbp / plotValue : 0;
  const dayChangeGbp = holding.day_change_gbp ?? 0;
  return {
    id: `${bedIndex}-${holdingIndex}-${holding.ticker}`,
    ticker: holding.ticker,
    name: holding.name || holding.ticker,
    bedId: bed.id,
    bedName: bed.name,
    units: holding.units ?? 0,
    valueGbp,
    costGbp,
    gainGbp,
    gainPct,
    dayChangePct: valueGbp > 0 ? (dayChangeGbp / valueGbp) * 100 : 0,
    stage: growthStageFor(gainPct),
    stars: starsFor(share),
    vigour: vigourFor(holding),
    share,
    sector: holding.sector || 'Unclassified',
    region: holding.region || 'Unknown',
    instrumentType: holding.instrument_type || 'Unknown',
    stale: Boolean(holding.is_stale),
    lastPriceDate: holding.last_price_date ?? null,
    daysHeld: holding.days_held ?? null,
    sellEligible: holding.sell_eligible !== false,
    daysUntilEligible: holding.days_until_eligible ?? null,
    nextEligibleSellDate: holding.next_eligible_sell_date ?? null,
  };
}

export interface PlotResource {
  id: string;
  label: string;
  icon: string;
  current: number;
  max: number;
  /**
   * "current / max" already formatted for its unit — counts stay bare,
   * money goes through formatGbp, so the feed bar reads "£15.8k / £20.0k"
   * rather than "15800 / 20000".
   */
  display: string;
  /** 0–100 for the meter. */
  pct: number;
  /** Plain-English explanation of what the bar actually measures. */
  hint: string;
}

export type AllowanceMap = Record<
  string,
  { used: number; limit: number; remaining: number }
>;

/**
 * Shared copy for every place the allowances fetch failed (HTTP error, e.g.
 * the 402 billing gate) rather than genuinely returning no data. Kept as one
 * constant so the FEED meter, the Season page's countdown, and the "Feed the
 * beds" milestone tier all read identically (#7005).
 */
export const ALLOWANCES_UNAVAILABLE_MESSAGE = 'Allowances unavailable right now';

/**
 * The three HUD meters, each backed by a real figure:
 * water = trades left this month, feed = tax-allowance headroom,
 * sunlight = share of crops priced today (data freshness).
 */
export function resourcesFromPlot(
  portfolio: Pick<Portfolio, 'trades_this_month' | 'trades_remaining'> | null,
  crops: readonly Crop[],
  allowances: AllowanceMap | null,
  allowancesUnavailable = false
): PlotResource[] {
  const tradesUsed = portfolio?.trades_this_month ?? 0;
  const tradesLeft = portfolio?.trades_remaining ?? 0;
  const tradesCap = tradesUsed + tradesLeft;

  const allowanceRows = Object.values(allowances ?? {});
  const allowanceLimit = allowanceRows.reduce(
    (sum, row) => sum + (row.limit ?? 0),
    0
  );
  const allowanceLeft = allowanceRows.reduce(
    (sum, row) => sum + (row.remaining ?? 0),
    0
  );

  const fresh = crops.filter((crop) => !crop.stale).length;

  return [
    {
      id: 'water',
      label: 'Water',
      icon: '💧',
      current: tradesLeft,
      max: tradesCap,
      display: `${tradesLeft} / ${tradesCap}`,
      pct: tradesCap > 0 ? clamp((tradesLeft / tradesCap) * 100, 0, 100) : 0,
      hint: `${tradesLeft} of ${tradesCap} trades left this month`,
    },
    {
      id: 'feed',
      label: 'Feed',
      icon: '🌿',
      current: Math.round(allowanceLeft),
      max: Math.round(allowanceLimit),
      display: `${formatGbp(allowanceLeft)} / ${formatGbp(allowanceLimit)}`,
      pct:
        allowanceLimit > 0
          ? clamp((allowanceLeft / allowanceLimit) * 100, 0, 100)
          : 0,
      hint: allowancesUnavailable
        ? ALLOWANCES_UNAVAILABLE_MESSAGE
        : allowanceLimit > 0
          ? `${formatGbp(allowanceLeft)} of tax allowance headroom left`
          : 'No allowance data for this grower yet',
    },
    {
      id: 'sun',
      label: 'Sunlight',
      icon: '☀️',
      current: fresh,
      max: crops.length,
      display: `${fresh} / ${crops.length}`,
      pct: crops.length > 0 ? clamp((fresh / crops.length) * 100, 0, 100) : 0,
      hint: `${fresh} of ${crops.length} crops priced from fresh data`,
    },
  ];
}

export interface PlotSnapshot {
  owner: string;
  asOf: string;
  plotValueGbp: number;
  totalGainGbp: number;
  dayChangeGbp: number;
  beds: Bed[];
  crops: Crop[];
  resources: PlotResource[];
  grower: GrowerLevel;
  rank: string;
  streak: number;
}

export interface BuildSnapshotInput {
  portfolio: Portfolio | null;
  xp?: number | null;
  streak?: number | null;
  allowances?: AllowanceMap | null;
  /** True when the allowances fetch failed (HTTP error), not merely empty. */
  allowancesUnavailable?: boolean;
}

/** Fold a real portfolio (plus XP/allowance context) into the game view. */
export function buildPlotSnapshot({
  portfolio,
  xp = 0,
  streak = 0,
  allowances = null,
  allowancesUnavailable = false,
}: BuildSnapshotInput): PlotSnapshot {
  const accounts = portfolio?.accounts ?? [];
  const beds = accounts.map(bedFromAccount);
  const plotValue =
    portfolio?.total_value_estimate_gbp ??
    beds.reduce((sum, bed) => sum + bed.valueGbp, 0);

  const crops: Crop[] = [];
  accounts.forEach((account, bedIndex) => {
    const bed = beds[bedIndex];
    (account.holdings ?? []).forEach((holding, holdingIndex) => {
      crops.push(
        cropFromHolding(holding, bed, plotValue, bedIndex, holdingIndex)
      );
    });
  });
  crops.sort((left, right) => right.valueGbp - left.valueGbp);

  const totalGainGbp = crops.reduce((sum, crop) => sum + crop.gainGbp, 0);
  const dayChangeGbp = crops.reduce(
    (sum, crop) => sum + (crop.valueGbp * crop.dayChangePct) / 100,
    0
  );
  const grower = levelFromXp(xp ?? 0);

  return {
    owner: portfolio?.owner ?? '',
    asOf: portfolio?.as_of ?? '',
    plotValueGbp: plotValue,
    totalGainGbp,
    dayChangeGbp,
    beds,
    crops,
    resources: resourcesFromPlot(portfolio, crops, allowances, allowancesUnavailable),
    grower,
    rank: growerRank(grower.level),
    streak: streak ?? 0,
  };
}

export interface GerminatingCrop {
  crop: Crop;
  /** 0–100 through the minimum holding period. */
  pct: number;
  daysHeld: number;
  daysRemaining: number;
  readyOn: string | null;
}

/**
 * Crops still inside their minimum holding period, soonest-ready first.
 *
 * This is the honest analogue of an incubator: real progress toward a real
 * unlock date the backend already computes (`days_until_eligible` /
 * `next_eligible_sell_date` from the configured `hold_days_min`), not a
 * timer invented for the skin.
 */
export function germinatingCrops(crops: readonly Crop[]): GerminatingCrop[] {
  return crops
    .filter(
      (crop) =>
        !crop.sellEligible &&
        crop.daysUntilEligible !== null &&
        crop.daysUntilEligible > 0
    )
    .map((crop) => {
      const remaining = crop.daysUntilEligible ?? 0;
      const held = Math.max(0, crop.daysHeld ?? 0);
      const total = held + remaining;
      return {
        crop,
        pct: total > 0 ? clamp((held / total) * 100, 0, 100) : 0,
        daysHeld: held,
        daysRemaining: remaining,
        readyOn: crop.nextEligibleSellDate,
      };
    })
    .sort((left, right) => left.daysRemaining - right.daysRemaining);
}

/**
 * Resolve a `/plot/crops/:cropId` segment to a crop.
 *
 * Matches the unique id first, then falls back to the first crop with that
 * ticker so links written before ids existed (and anything a user has
 * bookmarked) still land somewhere sensible.
 */
export function findCropByRouteId(
  crops: readonly Crop[],
  routeId: string
): Crop | undefined {
  return (
    crops.find((crop) => crop.id === routeId) ??
    crops.find((crop) => crop.ticker === routeId)
  );
}

/** Compact money for HUD chips: £1.2k, £864.1k, £5.3m. */
export function formatGbp(value: number | null | undefined): string {
  const amount = Number.isFinite(value) ? (value as number) : 0;
  const sign = amount < 0 ? '-' : '';
  const abs = Math.abs(amount);
  if (abs >= 1_000_000) return `${sign}£${(abs / 1_000_000).toFixed(1)}m`;
  if (abs >= 1_000) return `${sign}£${(abs / 1_000).toFixed(1)}k`;
  return `${sign}£${abs.toFixed(abs < 10 ? 2 : 0)}`;
}

/** Signed percentage for gain chips, always with an explicit +/-. */
export function formatPct(value: number | null | undefined): string {
  const pct = Number.isFinite(value) ? (value as number) : 0;
  return `${pct >= 0 ? '+' : ''}${pct.toFixed(1)}%`;
}
