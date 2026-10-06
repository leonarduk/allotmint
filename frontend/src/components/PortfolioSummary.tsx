import type { ReactNode } from "react";
import type { Account } from "../types";
import { percent } from "../lib/money";
import { useReportingCurrency } from "../hooks/useReportingCurrency";
import { ReportingCurrencyNote } from "./ReportingCurrencyNote";
import { isCashInstrument } from "../lib/instruments";
import { isCostBasisUnreliable } from "../lib/costBasis";
import { FX_RATE_SOURCE_MISSING } from "../lib/fxRateSource";
import { LineChart, PiggyBank, TrendingUp, Wallet } from "lucide-react";

export type PortfolioTotals = {
  totalValue: number;
  totalStockValue: number;
  totalCash: number;
  totalGain: number;
  totalDayChange: number;
  totalCost: number;
  totalGainPct: number;
  totalDayChangePct: number;
  /** Non-cash holdings whose gain is excluded from totalGain/totalCost
   * because their cost basis is unreliable: cost_basis_source "unknown" (no
   * acquisition date and no booked cost on record, per #7220) or
   * "book_suspect" (implausible booked cost, #8472). Market value from these holdings
   * still counts toward totalValue/totalStockValue/totalCash -- only the
   * *gain* figures, which the app cannot honestly compute, are excluded. */
  unknownCostBasisCount: number;
  /** Non-cash holdings considered for gain at all (denominator for the
   * "excludes N of M" wording). */
  gainEligibleHoldingCount: number;
  /** Non-cash holdings with no market value (no price), excluded from
   * totalGain/totalCost (#8607). Without a price their gain cannot be
   * computed; treating the missing value as £0 would book their whole cost
   * as a loss. Counted separately from unknownCostBasisCount: a holding is
   * counted in at most one of the two, and unknown cost basis takes
   * precedence, so an unpriced holding with an unreliable cost basis is
   * reported under cost basis and the "N of M" counts never exceed M. */
  unpricedHoldingCount: number;
  /** Non-cash holdings with no FX rate at all (fx_rate_source "missing",
   * #9664): the backend leaves them unpriced, so they are already absent
   * from totalValue -- this only says why (#9730). Counted whatever their
   * cost basis, unlike unpricedHoldingCount. */
  missingFxHoldingCount: number;
  /** The part of unpricedHoldingCount whose missing price is a missing FX
   * rate, so the gain note can name the cause (#9730). */
  unpricedMissingFxCount: number;
};

// eslint-disable-next-line react-refresh/only-export-components
export function computePortfolioTotals(accounts: Account[]): PortfolioTotals {
  let totalValue = 0;
  let totalStockValue = 0;
  let totalCash = 0;
  let totalGain = 0;
  let totalDayChange = 0;
  let totalCost = 0;
  let unknownCostBasisCount = 0;
  let gainEligibleHoldingCount = 0;
  let unpricedHoldingCount = 0;
  let missingFxHoldingCount = 0;
  let unpricedMissingFxCount = 0;

  for (const acct of accounts) {
    totalValue += acct.value_estimate_gbp ?? 0;
    for (const h of acct.holdings ?? []) {
      const market = h.market_value_gbp ?? 0;
      const dayChg = h.day_change_gbp ?? 0;
      const isCash = isCashInstrument({
        instrument_type: h.instrument_type,
        ticker: h.ticker,
      });

      if (isCash) {
        totalCash += market;
      } else {
        totalStockValue += market;
      }
      totalDayChange += dayChg;
      gainEligibleHoldingCount += 1;
      const missingFx = !isCash && h.fx_rate_source === FX_RATE_SOURCE_MISSING;
      if (missingFx) {
        missingFxHoldingCount += 1;
      }

      // A holding with no acquisition date and no booked cost has its cost
      // basis fabricated to equal market value (see backend/common/
      // holding_utils.py), which makes gain read as a confident £0.00 --
      // indistinguishable from "you broke even". Excluding it from the
      // gain/cost totals (rather than summing that fabricated zero) keeps
      // the headline figure honest; the per-row cells already render N/A
      // for the same reason (HoldingsTable.tsx). An implausible booked cost
      // ("book_suspect", #8472) is excluded for the same reason: summing its
      // tiny cost would inflate the headline gain by orders of magnitude.
      if (isCostBasisUnreliable(h.cost_basis_source)) {
        unknownCostBasisCount += 1;
        continue;
      }

      // An unpriced non-cash holding (#8607) has no market value, so its
      // gain cannot be computed. Falling through would compute
      // `0 - cost` and book its whole cost as a loss (headline -100%).
      if (!isCash && (h.market_value_gbp === null || h.market_value_gbp === undefined)) {
        unpricedHoldingCount += 1;
        if (missingFx) {
          unpricedMissingFxCount += 1;
        }
        continue;
      }

      const cost =
        h.cost_basis_gbp && h.cost_basis_gbp > 0
          ? h.cost_basis_gbp
          : h.effective_cost_basis_gbp ?? 0;
      const gain =
        h.gain_gbp !== undefined && h.gain_gbp !== null && h.gain_gbp !== 0
          ? h.gain_gbp
          : market - cost;

      totalCost += cost;
      totalGain += gain;
    }
  }

  const totalGainPct = totalCost > 0 ? (totalGain / totalCost) * 100 : 0;
  const totalDayChangePct =
    totalValue - totalDayChange !== 0
      ? (totalDayChange / (totalValue - totalDayChange)) * 100
      : 0;

  return {
    totalValue,
    totalStockValue,
    totalCash,
    totalGain,
    totalDayChange,
    totalCost,
    totalGainPct,
    totalDayChangePct,
    unknownCostBasisCount,
    gainEligibleHoldingCount,
    unpricedHoldingCount,
    missingFxHoldingCount,
    unpricedMissingFxCount,
  };
}

function buildGainNote(
  unknownCostBasisCount: number,
  unpricedHoldingCount: number,
  unpricedMissingFxCount: number,
  gainEligibleHoldingCount: number,
  allGainUnknown: boolean,
): string | undefined {
  // Names a missing FX rate as the cause of a missing price (#9730).
  const fxCause =
    unpricedMissingFxCount > 0 ? ` (${unpricedMissingFxCount} with no FX rate)` : "";
  if (allGainUnknown) {
    const reason =
      unpricedHoldingCount === 0
        ? "no reliable cost basis"
        : unknownCostBasisCount === 0
          ? "no price"
          : "no reliable cost basis or no price";
    return `Gain unavailable for all ${gainEligibleHoldingCount} holdings (${reason})${fxCause}`;
  }
  if (unknownCostBasisCount > 0 && unpricedHoldingCount > 0) {
    return `Excludes ${unknownCostBasisCount} of ${gainEligibleHoldingCount} holdings with no reliable cost basis and ${unpricedHoldingCount} with no price${fxCause}`;
  }
  if (unknownCostBasisCount > 0) {
    return `Excludes ${unknownCostBasisCount} of ${gainEligibleHoldingCount} holdings with no reliable cost basis`;
  }
  if (unpricedHoldingCount > 0) {
    return `Excludes ${unpricedHoldingCount} of ${gainEligibleHoldingCount} holdings with no price${fxCause}`;
  }
  return undefined;
}

type Props = {
  totals: PortfolioTotals;
};

export function PortfolioSummary({ totals }: Props) {
  const {
    totalValue,
    totalStockValue,
    totalCash,
    totalGain,
    totalGainPct,
    unknownCostBasisCount,
    gainEligibleHoldingCount,
    unpricedHoldingCount,
    missingFxHoldingCount,
    unpricedMissingFxCount,
  } = totals;
  const reporting = useReportingCurrency();

  // When every gain-eligible holding is excluded (unknown cost basis or no
  // price), totalCost/totalGain are both zero -- not because the portfolio broke
  // even, but because there is nothing to compute from. Say so rather than
  // showing a confident £0.00.
  const allGainUnknown =
    gainEligibleHoldingCount > 0 &&
    unknownCostBasisCount + unpricedHoldingCount === gainEligibleHoldingCount;
  const gainNote = buildGainNote(
    unknownCostBasisCount,
    unpricedHoldingCount,
    unpricedMissingFxCount,
    gainEligibleHoldingCount,
    allGainUnknown,
  );
  // The backend leaves a holding with no FX rate unpriced, so it adds nothing
  // to the total value; say so rather than let the total read as complete (#9730).
  const valueNote =
    missingFxHoldingCount > 0
      ? `Excludes ${missingFxHoldingCount} ${missingFxHoldingCount === 1 ? "holding" : "holdings"} with no FX rate`
      : undefined;

  return (
    <div
      style={{
        display: "flex",
        flexWrap: "wrap",
        gap: "1.5rem",
        margin: "1rem 0",
        padding: "1rem",
        backgroundColor: "var(--summary-card-bg)",
        border: "1px solid var(--summary-card-border)",
        borderRadius: "6px",
      }}
    >
      <SummaryCard
        label="Stock value"
        icon={<LineChart size={20} />}
        value={reporting.format(totalStockValue)}
      />
      <SummaryCard
        label="Total cash"
        icon={<Wallet size={20} />}
        value={reporting.format(totalCash)}
      />
      <SummaryCard
        label="Total value"
        icon={<PiggyBank size={20} />}
        value={reporting.format(totalValue)}
        note={valueNote}
      />
      <SummaryCard
        label="Gain/loss"
        icon={<TrendingUp size={20} />}
        value={allGainUnknown ? "—" : reporting.format(totalGain)}
        accentColor={
          allGainUnknown
            ? undefined
            : totalGain >= 0
              ? "var(--gain-positive)"
              : "var(--gain-negative)"
        }
        secondary={allGainUnknown ? undefined : `(${percent(totalGainPct)})`}
        note={gainNote}
      />
      <ReportingCurrencyNote reporting={reporting} />
    </div>
  );
}

export default PortfolioSummary;

type SummaryCardProps = {
  label: string;
  icon: ReactNode;
  value: string;
  secondary?: string;
  accentColor?: string;
  note?: string;
};

function SummaryCard({
  label,
  icon,
  value,
  secondary,
  accentColor,
  note,
}: SummaryCardProps) {
  return (
    <div style={{ minWidth: "12rem", flex: "1 1 12rem" }}>
      <div
        style={{
          fontSize: "1rem",
          color: "var(--summary-card-label)",
          display: "flex",
          alignItems: "center",
          gap: "0.25rem",
        }}
      >
        {icon}
        {label}
      </div>
      <div
        style={{
          fontSize: "2rem",
          fontWeight: "bold",
          color: accentColor ?? "var(--summary-card-value)",
          display: "flex",
          alignItems: "baseline",
          gap: "0.5rem",
        }}
      >
        <span>{value}</span>
        {secondary && (
          <span
            style={{
              fontSize: "1rem",
              fontWeight: "normal",
              color: accentColor ?? "var(--summary-card-label)",
            }}
          >
            {secondary}
          </span>
        )}
      </div>
      {note && (
        <div
          role="status"
          style={{
            fontSize: "0.75rem",
            color: "var(--summary-card-label)",
            marginTop: "0.25rem",
          }}
        >
          {note}
        </div>
      )}
    </div>
  );
}
