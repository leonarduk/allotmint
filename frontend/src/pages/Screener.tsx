import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { checkScreenerAvailable, getScreener } from "../api";
import type { ScreenerResult } from "../types";
import { useSortableTable } from "../hooks/useSortableTable";
import { InstrumentDetail } from "../components/InstrumentDetail";
import InfoTip from "../components/InfoTip";
import WatchlistToggle from "../components/WatchlistToggle";
import { WATCHLISTS, type WatchlistName } from "../data/watchlists";
import i18n from "../i18n";

const RATIO_COLUMN_TIPS: Record<
  string,
  { key: string; defaultText: string; anchor: string }
> = {
  PEG: { key: "peg", defaultText: "P/E ratio divided by the expected earnings growth rate.", anchor: "peg-ratio" },
  "P/E": { key: "pe", defaultText: "Share price divided by earnings per share.", anchor: "pe-ratio" },
  "D/E": { key: "de", defaultText: "Total debt divided by shareholders' equity — a measure of financial leverage.", anchor: "debt-equity" },
  "LT D/E": { key: "ltDe", defaultText: "Long-term debt divided by shareholders' equity.", anchor: "lt-debt-equity" },
  IntCov: { key: "interestCoverage", defaultText: "Operating earnings (EBIT) divided by interest expense.", anchor: "interest-coverage" },
  Curr: { key: "currentRatio", defaultText: "Current assets divided by current liabilities.", anchor: "current-ratio" },
  Quick: { key: "quickRatio", defaultText: "Liquid assets, excluding inventory, divided by current liabilities.", anchor: "quick-ratio" },
  FCF: { key: "fcf", defaultText: "Cash generated from operations minus capital expenditure.", anchor: "free-cash-flow" },
  EPS: { key: "eps", defaultText: "Net income divided by the number of shares outstanding.", anchor: "eps" },
  "Gross Margin": { key: "grossMargin", defaultText: "Gross profit divided by revenue.", anchor: "gross-margin" },
  "Op Margin": { key: "operatingMargin", defaultText: "Operating income divided by revenue.", anchor: "operating-margin" },
  "Net Margin": { key: "netMargin", defaultText: "Net income divided by revenue.", anchor: "net-margin" },
  "EBITDA Margin": { key: "ebitdaMargin", defaultText: "EBITDA divided by revenue.", anchor: "ebitda-margin" },
  ROA: { key: "roa", defaultText: "Net income divided by total assets.", anchor: "roa" },
  ROE: { key: "roe", defaultText: "Net income divided by shareholders' equity.", anchor: "roe" },
  ROI: { key: "roi", defaultText: "The gain from an investment divided by its cost.", anchor: "roi" },
  "Div%": { key: "dividendYield", defaultText: "Annual dividend per share divided by share price.", anchor: "dividend-yield" },
  Payout: { key: "dividendPayoutRatio", defaultText: "Dividends paid divided by net income.", anchor: "dividend-payout-ratio" },
  Beta: { key: "beta", defaultText: "A measure of how sensitive a stock's price is to overall market movements.", anchor: "beta" },
  Shares: { key: "sharesOutstanding", defaultText: "The total number of a company's shares currently held by all shareholders.", anchor: "shares-outstanding" },
  Float: { key: "floatShares", defaultText: "Shares outstanding that are freely tradable, excluding closely held or restricted shares.", anchor: "float-shares" },
  MktCap: { key: "marketCap", defaultText: "Share price multiplied by shares outstanding.", anchor: "market-cap" },
  "52wH": { key: "high52w", defaultText: "The highest trading price over the past 52 weeks.", anchor: "week-52-high" },
  "52wL": { key: "low52w", defaultText: "The lowest trading price over the past 52 weeks.", anchor: "week-52-low" },
  "P/B": { key: "pb", defaultText: "Share price divided by book value per share.", anchor: "pb-ratio" },
  "P/S": { key: "ps", defaultText: "Market capitalisation divided by trailing twelve-month revenue.", anchor: "ps-ratio" },
  "EV/EBITDA": { key: "evEbitda", defaultText: "Enterprise value (market cap plus net debt) divided by EBITDA.", anchor: "ev-ebitda" },
  "Rev Growth": { key: "revenueGrowth", defaultText: "Year-on-year revenue growth, as a fraction (0.1 = 10%).", anchor: "revenue-growth" },
  "EPS Growth": { key: "earningsGrowth", defaultText: "Year-on-year earnings growth, as a fraction (0.1 = 10%).", anchor: "earnings-growth" },
  AvgVol: { key: "avgVolume", defaultText: "The average number of shares traded per day over a recent period.", anchor: "avg-volume" },
};

function RatioHeaderInfoTip({ column }: { column: string }) {
  const { t } = useTranslation();
  const tip = RATIO_COLUMN_TIPS[column];
  if (!tip) return null;
  return (
    <InfoTip
      label={t("screener.tips.infoLabel", "What does {{column}} mean?", { column })}
      to={`/metrics-explained#${tip.anchor}`}
    >
      {t(`screener.tips.${tip.key}`, tip.defaultText)}
    </InfoTip>
  );
}

type ScreenerCriteria = NonNullable<Parameters<typeof getScreener>[1]>;
type FilterParam = keyof ScreenerCriteria;

// "fraction": the backend compares against a ratio (0.1 = 10%), so typing
// "10" for 10% silently filters everything out -- show the scale inline.
// "integer": the backend declares these as `int` query params, so a decimal
// would be rejected with a 422.
type FilterKind = "fraction" | "integer";

const FILTER_FIELDS: { param: FilterParam; labelKey: string; kind?: FilterKind }[] = [
  { param: "peg_max", labelKey: "maxPeg" },
  { param: "pe_max", labelKey: "maxPe" },
  { param: "pb_max", labelKey: "maxPb" },
  { param: "ps_max", labelKey: "maxPs" },
  { param: "ev_ebitda_max", labelKey: "maxEvEbitda" },
  { param: "revenue_growth_min", labelKey: "minRevenueGrowth", kind: "fraction" },
  { param: "earnings_growth_min", labelKey: "minEarningsGrowth", kind: "fraction" },
  { param: "de_max", labelKey: "maxDe" },
  { param: "lt_de_max", labelKey: "maxLtDe" },
  { param: "interest_coverage_min", labelKey: "minInterestCoverage" },
  { param: "current_ratio_min", labelKey: "minCurrentRatio" },
  { param: "quick_ratio_min", labelKey: "minQuickRatio" },
  { param: "fcf_min", labelKey: "minFcf" },
  { param: "eps_min", labelKey: "minEps" },
  { param: "gross_margin_min", labelKey: "minGrossMargin", kind: "fraction" },
  { param: "operating_margin_min", labelKey: "minOperatingMargin", kind: "fraction" },
  { param: "net_margin_min", labelKey: "minNetMargin", kind: "fraction" },
  { param: "ebitda_margin_min", labelKey: "minEbitdaMargin", kind: "fraction" },
  { param: "roa_min", labelKey: "minRoa", kind: "fraction" },
  { param: "roe_min", labelKey: "minRoe", kind: "fraction" },
  { param: "roi_min", labelKey: "minRoi", kind: "fraction" },
  { param: "dividend_yield_min", labelKey: "minDividendYield" },
  { param: "dividend_payout_ratio_max", labelKey: "maxDividendPayoutRatio", kind: "fraction" },
  { param: "beta_max", labelKey: "maxBeta" },
  { param: "shares_outstanding_min", labelKey: "minSharesOutstanding", kind: "integer" },
  { param: "float_shares_min", labelKey: "minFloatShares", kind: "integer" },
  { param: "market_cap_min", labelKey: "minMarketCap", kind: "integer" },
  { param: "high_52w_max", labelKey: "max52WeekHigh" },
  { param: "low_52w_min", labelKey: "min52WeekLow" },
  { param: "avg_volume_min", labelKey: "minAvgVolume", kind: "integer" },
];

type FilterValues = Partial<Record<FilterParam, string>>;

// A conservative "profitable, reasonably valued, solvent" starting point.
// Deliberately limited to metrics that are widely populated and whose scale
// is unambiguous (trailing P/E, current ratio, ROE as a fraction); D/E and
// dividend yield are left blank because data vendors disagree on whether
// they are ratios or percentages.
const DEFAULT_FILTERS: FilterValues = {
  pe_max: "25",
  current_ratio_min: "1",
  roe_min: "0.1",
};
const DEFAULT_WATCHLIST: WatchlistName = "FTSE 100";

function toCriteria(filters: FilterValues): ScreenerCriteria {
  const criteria: ScreenerCriteria = {};
  for (const { param, kind } of FILTER_FIELDS) {
    const raw = filters[param]?.trim();
    if (!raw) continue;
    const value = Number(raw);
    if (!Number.isFinite(value)) continue;
    // step="1" blocks a decimal on interactive submit, but not on a
    // programmatic one -- round so an int-typed param can never 422.
    criteria[param] = kind === "integer" ? Math.round(value) : value;
  }
  return criteria;
}

export function Screener() {
  const [watchlist, setWatchlist] = useState<WatchlistName | "Custom">(
    DEFAULT_WATCHLIST,
  );
  const [tickers, setTickers] = useState("");
  const [filters, setFilters] = useState<FilterValues>(DEFAULT_FILTERS);
  const [rows, setRows] = useState<ScreenerResult[]>([]);
  const [hasRun, setHasRun] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<ScreenerResult | null>(null);
  // Tri-state, not a boolean: `null` means "still checking" and must not
  // render the form. Defaulting optimistically to `true` would flash the
  // full 24-filter form (fully interactive) for one round-trip even to a
  // gated user -- exactly the "unexplained work first" complaint this
  // issue is about. A brief, correct loading state is the right trade
  // for everyone, including deployments where the screener *is* enabled.
  const [screenerAvailable, setScreenerAvailable] = useState<boolean | null>(
    null,
  );
  const { t } = useTranslation();

  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();
    checkScreenerAvailable(controller.signal).then((available) => {
      if (!cancelled) setScreenerAvailable(available);
    });
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, []);

  const { sorted, handleSort } = useSortableTable(rows, "rank");

  const cell = { padding: "4px 6px" } as const;
  const right = { ...cell, textAlign: "right", cursor: "pointer" } as const;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const symbols =
      watchlist === "Custom"
        ? tickers
            .split(",")
            .map((t) => t.trim())
            .filter(Boolean)
        : WATCHLISTS[watchlist];
    if (!symbols.length) {
      setError(
        t("screener.noTickers", "Enter at least one ticker, or pick a watchlist."),
      );
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const data = await getScreener(symbols, toCriteria(filters));
      setRows(data);
      setHasRun(true);
    } catch (e) {
      setRows([]);
      setHasRun(false);
      const status = (e as { status?: number } | undefined)?.status;
      if (status === 402) {
        // Genuinely unavailable in this deployment -- never surface the raw
        // backend detail (it names an internal package and a repo URL).
        // Keep the technical detail in the console only (#7221). The
        // `!screenerAvailable` banner below now owns this message, so no
        // `setError` here -- that would only create a dead, unreachable
        // second copy of the same text.
        console.error("Screener request rejected (feature unavailable):", e);
        setScreenerAvailable(false);
      } else {
        setError(e instanceof Error ? e.message : String(e));
      }
    } finally {
      setLoading(false);
    }
  }

  // A single, always-mounted `role="status"` node rather than one that
  // mounts/unmounts with the gate state: some screen readers only announce
  // a live region's *content changing*, not a region appearing for the
  // first time, so the container has to already exist before its text is
  // set (a11y follow-up on #7221).
  const statusMessage =
    screenerAvailable === false
      ? t("screener.unavailableBody")
      : screenerAvailable === null
        ? t("screener.checking")
        : "";

  return (
    <div className="container mx-auto p-4">
      <h1 className="mb-1 text-2xl">{t("screener.title")}</h1>
      <p className="mb-4">{t("screener.description")}</p>

      <p
        role="status"
        style={
          statusMessage
            ? {
                background: "#fff4e5",
                border: "1px solid #f0ad4e",
                color: "#333",
                padding: "0.5rem 1rem",
                marginBottom: "1rem",
              }
            : undefined
        }
      >
        {statusMessage}
      </p>

      {screenerAvailable === true && (
        <form
          onSubmit={handleSubmit}
          className="mb-4 flex flex-wrap items-center gap-2"
        >
          <label className="mr-2">
            {t("screener.watchlistLabel")}
            <select
              value={watchlist}
              onChange={(e) =>
                setWatchlist(e.target.value as WatchlistName | "Custom")
              }
              className="ml-1 border px-2 py-1"
              aria-label={t("screener.watchlistLabel")}
            >
              <option value="Custom">{t("screener.custom")}</option>
              {(Object.keys(WATCHLISTS) as WatchlistName[]).map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>
          {watchlist === "Custom" && (
            <label className="mr-2">
              {t("screener.tickers")}
              <input
                aria-label={t("screener.tickers")}
                type="text"
                value={tickers}
                onChange={(e) => setTickers(e.target.value)}
                placeholder={t("screener.tickersPlaceholder")}
                style={{ marginLeft: "0.25rem" }}
              />
            </label>
          )}
          {FILTER_FIELDS.map(({ param, labelKey, kind }) => {
            const label = t(`screener.${labelKey}`);
            return (
              <label key={param} style={{ marginRight: "0.5rem" }}>
                {label}
                <input
                  aria-label={label}
                  type="number"
                  value={filters[param] ?? ""}
                  onChange={(e) =>
                    setFilters((prev) => ({ ...prev, [param]: e.target.value }))
                  }
                  step={kind === "integer" ? "1" : "any"}
                  min={kind === "integer" ? "0" : undefined}
                  placeholder={
                    kind === "fraction"
                      ? t("screener.fractionHint", "0.10 = 10%")
                      : undefined
                  }
                  style={{ marginLeft: "0.25rem" }}
                />
              </label>
            );
          })}
          <button type="submit" disabled={loading} style={{ marginLeft: "0.5rem" }}>
            {loading ? t("screener.loading") : t("screener.run")}
          </button>
          <button
            type="button"
            onClick={() => {
              setWatchlist(DEFAULT_WATCHLIST);
              setFilters(DEFAULT_FILTERS);
            }}
          >
            {t("screener.resetDefaults", "Reset to defaults")}
          </button>
          <button type="button" onClick={() => setFilters({})}>
            {t("screener.clearFilters", "Clear filters")}
          </button>
        </form>
      )}

      {screenerAvailable === true && error && (
        <p style={{ color: "red" }}>{error}</p>
      )}
      {loading && <p>{t("screener.loading")}</p>}
      {hasRun && !loading && rows.length === 0 && (
        <p role="status">
          {t(
            "screener.noResults",
            "No tickers matched these filters. Try loosening or clearing some.",
          )}
        </p>
      )}

      {rows.length > 0 && !loading && (
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <th style={right} onClick={() => handleSort("rank")}>
                {t("screener.col.rank")}
              </th>
              <th
                style={{ ...cell, cursor: "pointer" }}
                onClick={() => handleSort("ticker")}
              >
                {t("common.ticker")}
              </th>
              <th style={right} onClick={() => handleSort("peg_ratio")}>
                PEG
                <RatioHeaderInfoTip column="PEG" />
              </th>
              <th style={right} onClick={() => handleSort("pe_ratio")}>
                P/E
                <RatioHeaderInfoTip column="P/E" />
              </th>
              <th style={right} onClick={() => handleSort("pb_ratio")}>
                P/B
                <RatioHeaderInfoTip column="P/B" />
              </th>
              <th style={right} onClick={() => handleSort("ps_ratio")}>
                P/S
                <RatioHeaderInfoTip column="P/S" />
              </th>
              <th style={right} onClick={() => handleSort("ev_ebitda")}>
                EV/EBITDA
                <RatioHeaderInfoTip column="EV/EBITDA" />
              </th>
              <th style={right} onClick={() => handleSort("revenue_growth")}>
                {t("screener.col.revGrowth")}
                <RatioHeaderInfoTip column="Rev Growth" />
              </th>
              <th style={right} onClick={() => handleSort("earnings_growth")}>
                {t("screener.col.epsGrowth")}
                <RatioHeaderInfoTip column="EPS Growth" />
              </th>
              <th style={right} onClick={() => handleSort("de_ratio")}>
                D/E
                <RatioHeaderInfoTip column="D/E" />
              </th>
              <th style={right} onClick={() => handleSort("lt_de_ratio")}>
                LT D/E
                <RatioHeaderInfoTip column="LT D/E" />
              </th>
              <th style={right} onClick={() => handleSort("interest_coverage")}>
                {t("screener.col.intCov")}
                <RatioHeaderInfoTip column="IntCov" />
              </th>
              <th style={right} onClick={() => handleSort("current_ratio")}>
                {t("screener.col.curr")}
                <RatioHeaderInfoTip column="Curr" />
              </th>
              <th style={right} onClick={() => handleSort("quick_ratio")}>
                {t("screener.col.quick")}
                <RatioHeaderInfoTip column="Quick" />
              </th>
              <th style={right} onClick={() => handleSort("fcf")}>
                FCF
                <RatioHeaderInfoTip column="FCF" />
              </th>
              <th style={right} onClick={() => handleSort("eps")}>
                EPS
                <RatioHeaderInfoTip column="EPS" />
              </th>
              <th style={right} onClick={() => handleSort("gross_margin")}>
                {t("screener.col.grossMargin")}
                <RatioHeaderInfoTip column="Gross Margin" />
              </th>
              <th style={right} onClick={() => handleSort("operating_margin")}>
                {t("screener.col.opMargin")}
                <RatioHeaderInfoTip column="Op Margin" />
              </th>
              <th style={right} onClick={() => handleSort("net_margin")}>
                {t("screener.col.netMargin")}
                <RatioHeaderInfoTip column="Net Margin" />
              </th>
              <th style={right} onClick={() => handleSort("ebitda_margin")}>
                {t("screener.col.ebitdaMargin")}
                <RatioHeaderInfoTip column="EBITDA Margin" />
              </th>
              <th style={right} onClick={() => handleSort("roa")}>
                ROA
                <RatioHeaderInfoTip column="ROA" />
              </th>
              <th style={right} onClick={() => handleSort("roe")}>
                ROE
                <RatioHeaderInfoTip column="ROE" />
              </th>
              <th style={right} onClick={() => handleSort("roi")}>
                ROI
                <RatioHeaderInfoTip column="ROI" />
              </th>
              <th style={right} onClick={() => handleSort("dividend_yield")}>
                {t("screener.col.divPct")}
                <RatioHeaderInfoTip column="Div%" />
              </th>
              <th
                style={right}
                onClick={() => handleSort("dividend_payout_ratio")}
              >
                {t("screener.col.payout")}
                <RatioHeaderInfoTip column="Payout" />
              </th>
              <th style={right} onClick={() => handleSort("beta")}>
                Beta
                <RatioHeaderInfoTip column="Beta" />
              </th>
              <th
                style={right}
                onClick={() => handleSort("shares_outstanding")}
              >
                {t("screener.col.shares")}
                <RatioHeaderInfoTip column="Shares" />
              </th>
              <th
                style={right}
                onClick={() => handleSort("float_shares")}
              >
                {t("screener.col.float")}
                <RatioHeaderInfoTip column="Float" />
              </th>
              <th style={right} onClick={() => handleSort("market_cap")}>
                {t("screener.col.mktCap")}
                <RatioHeaderInfoTip column="MktCap" />
              </th>
              <th style={right} onClick={() => handleSort("high_52w")}>
                {t("screener.col.wk52h")}
                <RatioHeaderInfoTip column="52wH" />
              </th>
              <th style={right} onClick={() => handleSort("low_52w")}>
                {t("screener.col.wk52l")}
                <RatioHeaderInfoTip column="52wL" />
              </th>
              <th style={right} onClick={() => handleSort("avg_volume")}>
                {t("screener.col.avgVol")}
                <RatioHeaderInfoTip column="AvgVol" />
              </th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((r) => (
              <tr
                key={`${r.ticker}-${r.rank}`}
                onClick={() => setSelected(r)}
                style={{ cursor: "pointer" }}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    setSelected(r);
                  }
                }}
              >
                <td style={right}>{r.rank}</td>
                <td style={{ ...cell, whiteSpace: "nowrap" }}>
                  {r.ticker}
                  <WatchlistToggle ticker={r.ticker} />
                </td>
                <td style={right}>{r.peg_ratio ?? "—"}</td>
                <td style={right}>{r.pe_ratio ?? "—"}</td>
                <td style={right}>{r.pb_ratio ?? "—"}</td>
                <td style={right}>{r.ps_ratio ?? "—"}</td>
                <td style={right}>{r.ev_ebitda ?? "—"}</td>
                <td style={right}>{r.revenue_growth ?? "—"}</td>
                <td style={right}>{r.earnings_growth ?? "—"}</td>
                <td style={right}>{r.de_ratio ?? "—"}</td>
                <td style={right}>{r.lt_de_ratio ?? "—"}</td>
                <td style={right}>{r.interest_coverage ?? "—"}</td>
                <td style={right}>{r.current_ratio ?? "—"}</td>
                <td style={right}>{r.quick_ratio ?? "—"}</td>
                <td style={right}>
                  {r.fcf != null
                    ? new Intl.NumberFormat(i18n.language).format(r.fcf)
                    : "—"}
                </td>
                <td style={right}>{r.eps ?? "—"}</td>
                <td style={right}>{r.gross_margin ?? "—"}</td>
                <td style={right}>{r.operating_margin ?? "—"}</td>
                <td style={right}>{r.net_margin ?? "—"}</td>
                <td style={right}>{r.ebitda_margin ?? "—"}</td>
                <td style={right}>{r.roa ?? "—"}</td>
                <td style={right}>{r.roe ?? "—"}</td>
                <td style={right}>{r.roi ?? "—"}</td>
                <td style={right}>{r.dividend_yield ?? "—"}</td>
                <td style={right}>{r.dividend_payout_ratio ?? "—"}</td>
                <td style={right}>{r.beta ?? "—"}</td>
                <td style={right}>
                  {r.shares_outstanding != null
                    ? new Intl.NumberFormat(i18n.language).format(
                        r.shares_outstanding,
                      )
                    : "—"}
                </td>
                <td style={right}>
                  {r.float_shares != null
                    ? new Intl.NumberFormat(i18n.language).format(
                        r.float_shares,
                      )
                    : "—"}
                </td>
                <td style={right}>
                  {r.market_cap != null
                    ? new Intl.NumberFormat(i18n.language).format(r.market_cap)
                    : "—"}
                </td>
                <td style={right}>{r.high_52w ?? "—"}</td>
                <td style={right}>{r.low_52w ?? "—"}</td>
                <td style={right}>
                  {r.avg_volume != null
                    ? new Intl.NumberFormat(i18n.language).format(r.avg_volume)
                    : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {selected && (
        <InstrumentDetail
          ticker={selected.ticker}
          name={selected.name ?? selected.ticker}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  );
}

export default Screener;

