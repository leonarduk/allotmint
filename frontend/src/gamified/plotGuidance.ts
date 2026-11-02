/**
 * "What could I do next?" for Plot mode (#7209).
 *
 * Pure and React-free, like `plotModel.ts`. Every suggestion here is a
 * *fact* read off real data (prices are N days old, a holding is waiting on
 * approval, cash is uninvested) with a link to the screen that deals with
 * it. Nothing in this module recommends buying or selling anything, and
 * nothing is invented to create urgency: when the data has nothing to say,
 * the answer is "nothing needs doing".
 */
import i18n from '../i18n';
import {
  awaitingApprovalCrops,
  distinctInstruments,
  formatGbp,
  portfolioAttentionReason,
  type AllowanceMap,
  type Bed,
  type Crop,
} from './plotModel';

export type PlotJobKind =
  | 'stale-prices'
  | 'needs-approval'
  | 'open-chores'
  | 'isa-headroom'
  | 'uninvested-cash'
  | 'split-holding';

export interface PlotJob {
  kind: PlotJobKind;
  /** One-line headline, e.g. "Your prices are 16 days old". */
  title: string;
  /** Plain-English reason the line matters, stated as fact. */
  reason: string;
  /** Where the link goes: a real route that deals with it. */
  to: string;
  linkLabel: string;
}

export interface PlotJobInput {
  asOf: string;
  today: string;
  crops: readonly Crop[];
  cashGbp: number;
  plotValueGbp: number;
  allowances: AllowanceMap | null;
  openChores: number;
  basePath: string;
}

/**
 * Cash below this share of the plot is ordinary working cash, not worth a
 * line on the hub. A share, not a fixed sum, so it scales with the plot.
 */
export const UNINVESTED_CASH_SHARE = 0.05;

function cropLink(basePath: string, crop: Crop): string {
  return `${basePath}/crops/${encodeURIComponent(crop.id)}`;
}

function stalePricesJob(input: PlotJobInput): PlotJob | null {
  const reason = portfolioAttentionReason(input.asOf, input.today);
  if (!reason) return null;
  return {
    kind: 'stale-prices',
    title: reason.label,
    reason: i18n.t('plot.nextJob.staleReason', { date: input.asOf }),
    to: '/data-quality',
    linkLabel: i18n.t('plot.nextJob.staleLink'),
  };
}

function needsApprovalJob(input: PlotJobInput): PlotJob | null {
  const waiting = awaitingApprovalCrops(input.crops);
  if (waiting.length === 0) return null;
  return {
    kind: 'needs-approval',
    title: i18n.t('plot.nextJob.approvalTitle', { count: waiting.length }),
    reason: i18n.t('plot.nextJob.approvalReason', {
      tickers: waiting.map((crop) => crop.ticker).join(', '),
    }),
    to: '/trade-compliance',
    linkLabel: i18n.t('plot.nextJob.approvalLink'),
  };
}

function openChoresJob(input: PlotJobInput): PlotJob | null {
  if (input.openChores <= 0) return null;
  return {
    kind: 'open-chores',
    title: i18n.t('plot.nextJob.choresTitle', { count: input.openChores }),
    reason: i18n.t('plot.nextJob.choresReason'),
    to: `${input.basePath}/chores`,
    linkLabel: i18n.t('plot.nextJob.choresLink'),
  };
}

function isaHeadroomJob(input: PlotJobInput): PlotJob | null {
  const isa = input.allowances?.isa;
  if (!isa || !(isa.limit > 0) || !(isa.remaining > 0)) return null;
  return {
    kind: 'isa-headroom',
    title: i18n.t('plot.nextJob.isaTitle', {
      amount: formatGbp(isa.remaining),
      limit: formatGbp(isa.limit),
    }),
    reason: i18n.t('plot.nextJob.isaReason'),
    to: '/tax-tools',
    linkLabel: i18n.t('plot.nextJob.isaLink'),
  };
}

function uninvestedCashJob(input: PlotJobInput): PlotJob | null {
  if (input.cashGbp <= 0 || input.plotValueGbp <= 0) return null;
  const share = input.cashGbp / input.plotValueGbp;
  if (share < UNINVESTED_CASH_SHARE) return null;
  return {
    kind: 'uninvested-cash',
    title: i18n.t('plot.nextJob.cashTitle', {
      amount: formatGbp(input.cashGbp),
      pct: Math.round(share * 100),
    }),
    reason: i18n.t('plot.nextJob.cashReason'),
    to: '/allocation',
    linkLabel: i18n.t('plot.nextJob.cashLink'),
  };
}

function splitHoldingJob(input: PlotJobInput): PlotJob | null {
  const split = distinctInstruments(input.crops).find(
    (group) => group.bedNames.length > 1
  );
  if (!split) return null;
  return {
    kind: 'split-holding',
    title: i18n.t('plot.nextJob.splitTitle', {
      ticker: split.ticker,
      count: split.bedNames.length,
    }),
    reason: i18n.t('plot.nextJob.splitReason', {
      beds: split.bedNames.join(', '),
    }),
    to: cropLink(input.basePath, split.combined),
    linkLabel: i18n.t('plot.nextJob.splitLink'),
  };
}

/**
 * Every job the data supports, most pressing first: numbers you can't trust
 * (stale prices) before anything built on them, something blocked on you
 * (approval) before routine (chores), and plain observations last.
 */
const JOB_RULES: readonly ((input: PlotJobInput) => PlotJob | null)[] = [
  stalePricesJob,
  needsApprovalJob,
  openChoresJob,
  isaHeadroomJob,
  uninvestedCashJob,
  splitHoldingJob,
];

export function plotJobs(input: PlotJobInput): PlotJob[] {
  return JOB_RULES.map((rule) => rule(input)).filter(
    (job): job is PlotJob => job !== null
  );
}

/** The single "next job on the plot", or null when nothing needs doing. */
export function nextPlotJob(input: PlotJobInput): PlotJob | null {
  return plotJobs(input)[0] ?? null;
}

/**
 * Instrument types the crop page can explain in plain English. Keys are
 * lower-cased, matching `lib/instrumentType.ts`, since types arrive in both
 * legacy ("Equity") and canonical ("equity") casing.
 */
const INSTRUMENT_TYPE_KEYS: Record<string, string> = {
  equity: 'equity',
  share: 'equity',
  stock: 'equity',
  etf: 'etf',
  fund: 'fund',
  'mutual fund': 'fund',
  bond: 'bond',
  'investment trust': 'investmentTrust',
  commodity: 'commodity',
  property: 'property',
  'real estate': 'property',
  'multi-asset': 'multiAsset',
};

/** One-sentence explanation of what an instrument type is. */
export function instrumentTypeExplanation(type: string | null | undefined) {
  const key = INSTRUMENT_TYPE_KEYS[(type ?? '').trim().toLowerCase()];
  return i18n.t(`plot.learn.type.${key ?? 'unknown'}`);
}

/** Account types whose tax wrapper the beds panel can explain. */
const WRAPPER_KEYS: Record<string, string> = {
  isa: 'isa',
  'stocks-isa': 'isa',
  lisa: 'lisa',
  jisa: 'jisa',
  sipp: 'pension',
  pension: 'pension',
  gia: 'gia',
  general: 'gia',
  ltd: 'company',
  cash: 'cash',
  savings: 'cash',
};

/** One-sentence explanation of a bed's tax wrapper. */
export function bedWrapperExplanation(accountType: string): string {
  const key = WRAPPER_KEYS[accountType.trim().toLowerCase()];
  return i18n.t(`plot.learn.wrapper.${key ?? 'unknown'}`);
}

export interface BedGain {
  /** Null when any crop in the bed has an unknown cost basis (#8471). */
  gainGbp: number | null;
  gainPct: number | null;
}

/** Unrealised gain per bed, from the same crop figures the cards show. */
export function bedGain(bed: Pick<Bed, 'id'>, crops: readonly Crop[]): BedGain {
  const inBed = crops.filter((crop) => crop.bedId === bed.id);
  if (inBed.length === 0 || inBed.some((crop) => crop.gainGbp === null)) {
    return { gainGbp: null, gainPct: null };
  }
  const gainGbp = inBed.reduce((sum, crop) => sum + (crop.gainGbp ?? 0), 0);
  const costGbp = inBed.reduce((sum, crop) => sum + crop.costGbp, 0);
  return { gainGbp, gainPct: costGbp > 0 ? (gainGbp / costGbp) * 100 : null };
}
