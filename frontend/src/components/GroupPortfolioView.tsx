// src/components/GroupPortfolioView.tsx
import {
  useState,
  useEffect,
  useCallback,
  useMemo,
  useRef,
  Fragment,
} from "react";

import type {
  GroupPortfolio,
  SectorContribution,
  RegionContribution,
  InstrumentSummary,
  OwnerSummary,
} from "../types";
import {
  getGroupPortfolio,
  getGroupAlphaVsBenchmark,
  getGroupTrackingError,
  getGroupMaxDrawdown,
  getGroupSectorContributions,
  getGroupRegionContributions,
  getGroupInstruments,
} from "../api";
import * as api from "../api";
import { InstrumentTable } from "./InstrumentTable";
import { TopMoversSummary } from "./TopMoversSummary";
import { money, percent, percentOrNa } from "../lib/money";
import PortfolioSummary, { computePortfolioTotals } from "./PortfolioSummary";
import { translateInstrumentType } from "../lib/instrumentType";
import { useFetch } from "../hooks/useFetch";
import tableStyles from "../styles/table.module.css";
import { useTranslation } from "react-i18next";
import { useConfig } from "../ConfigContext";
import { getGroupDisplayName } from "../utils/groups";
import { RelativeViewToggle } from "./RelativeViewToggle";
import { preloadInstrumentHistory } from "../hooks/useInstrumentHistory";
import { isCashInstrument } from "../lib/instruments";
import {
  createOwnerDisplayLookup,
  getOwnerDisplayName,
  sanitizeOwners,
} from "../utils/owners";
import {
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  Tooltip,
  Legend,
  BarChart,
  Bar,
  XAxis,
  YAxis,
} from "recharts";
import { BadgeCheck, LineChart, Shield } from "lucide-react";

const PIE_COLORS = [
  "#8884d8",
  "#82ca9d",
  "#ffc658",
  "#ff8042",
  "#8dd1e1",
  "#a4de6c",
  "#d0ed57",
  "#ffc0cb",
];

const DAY_CHANGE_BASELINE_EPSILON = 1e-2;

const computeDayChangePct = (value: number, delta: number): number | null => {
  if (!Number.isFinite(value) || !Number.isFinite(delta)) {
    return null;
  }

  const baseline = value - delta;

  if (!Number.isFinite(baseline) || Math.abs(baseline) < DAY_CHANGE_BASELINE_EPSILON) {
    return null;
  }

  return (delta / baseline) * 100;
};

type Props = {
  slug: string;
  owners?: OwnerSummary[];
  onSelectMember?: (ownerSlug: string) => void;
  onTradeInfo?: (
    info:
      | {
          as_of?: string | null;
          trades_this_month?: number | null;
          trades_remaining?: number | null;
        }
      | null,
  ) => void;
};

/* ────────────────────────────────────────────────────────────
 * Component
 * ────────────────────────────────────────────────────────── */
export function GroupPortfolioView(props: Props) {
  const { slug, owners, onTradeInfo } = props;
  const fetchPortfolio = useCallback(() => getGroupPortfolio(slug), [slug]);
  const {
    data: portfolio,
    loading,
    error: portfolioError,
  } = useFetch<GroupPortfolio>(fetchPortfolio, [slug], !!slug);

  const fetchSector = useCallback(() => getGroupSectorContributions(slug), [slug]);
  const fetchRegion = useCallback(() => getGroupRegionContributions(slug), [slug]);
  const { data: sectorContrib } = useFetch<SectorContribution[]>(
    fetchSector,
    [slug],
    !!slug
  );
  const { data: regionContrib } = useFetch<RegionContribution[]>(
    fetchRegion,
    [slug],
    !!slug
  );

  const { t } = useTranslation();
  const { relativeViewEnabled, baseCurrency } = useConfig();
  const [alpha, setAlpha] = useState<number | null>(null);
  const [trackingError, setTrackingError] = useState<number | null>(null);
  const [maxDrawdown, setMaxDrawdown] = useState<number | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [contribTab, setContribTab] = useState<"sector" | "region">("sector");
  const [activeOwner, setActiveOwner] = useState<string | null>(null);
  const [activeAccountType, setActiveAccountType] = useState<string | null>(null);
  const [instrumentRows, setInstrumentRows] = useState<InstrumentSummary[] | null>(null);
  const [instrumentLoading, setInstrumentLoading] = useState(false);
  const [instrumentError, setInstrumentError] = useState<Error | null>(null);
  const instrumentKeyRef = useRef<string | null>(null);
  const [expandedOwners, setExpandedOwners] = useState<Set<string>>(new Set());

  const loadGroupInstruments =
    ("getCachedGroupInstruments" in api
      ? (api as { getCachedGroupInstruments?: typeof getGroupInstruments })
          .getCachedGroupInstruments
      : undefined) ?? getGroupInstruments;

  const sanitizedOwners = useMemo(
    () => (owners ? sanitizeOwners(owners) : []),
    [owners],
  );

  const allowedOwnerSlugs = useMemo<Set<string> | null>(() => {
    if (!owners || owners.length === 0) {
      return null;
    }
    const allowed = new Set<string>();
    sanitizedOwners.forEach(({ owner }) => {
      if (owner) {
        allowed.add(owner);
      }
    });
    return allowed;
  }, [owners, sanitizedOwners]);

  const ownerLookup = useMemo(
    () => createOwnerDisplayLookup(sanitizedOwners),
    [sanitizedOwners],
  );

  useEffect(() => {
    setActiveOwner(null);
  }, [slug]);

  const visibleAccounts = useMemo(() => {
    const source = portfolio?.accounts ?? [];
    if (!allowedOwnerSlugs) {
      return source;
    }
    return source.filter((acct) => {
      if (!acct.owner) {
        return true;
      }
      return allowedOwnerSlugs.has(acct.owner);
    });
  }, [portfolio, allowedOwnerSlugs]);

  const ownerTabs = useMemo<
    { value: string; label: string; accountTypes: string[] }[]
  >(
    () => {
      if (!visibleAccounts.length) return [];
      const entries: {
        value: string;
        label: string;
        accountTypes: Set<string>;
      }[] = [];
      const index = new Map<string, (typeof entries)[number]>();
      for (const acct of visibleAccounts) {
        if (!acct.owner) continue;
        let entry = index.get(acct.owner);
        if (!entry) {
          entry = {
            value: acct.owner,
            label: getOwnerDisplayName(ownerLookup, acct.owner, acct.owner),
            accountTypes: new Set<string>(),
          };
          index.set(acct.owner, entry);
          entries.push(entry);
        }
        entry.accountTypes.add(acct.account_type);
      }
      return entries.map(({ value, label, accountTypes }) => ({
        value,
        label,
        accountTypes: Array.from(accountTypes),
      }));
    },
    [visibleAccounts, ownerLookup],
  );

  useEffect(() => {
    if (activeOwner && !ownerTabs.some((tab) => tab.value === activeOwner)) {
      setActiveOwner(null);
    }
  }, [activeOwner, ownerTabs]);

  useEffect(() => {
    setActiveAccountType(null);
  }, [activeOwner]);

  useEffect(() => {
    if (!activeOwner) return;
    const owner = ownerTabs.find((tab) => tab.value === activeOwner);
    if (!owner) return;
    if (activeAccountType && !owner.accountTypes.includes(activeAccountType)) {
      setActiveAccountType(null);
    }
  }, [activeOwner, activeAccountType, ownerTabs]);

  const ownerFilter = activeOwner ?? undefined;
  const accountFilter =
    activeOwner && activeAccountType ? activeAccountType : undefined;

  useEffect(() => {
    if (!slug) {
      setInstrumentRows(null);
      setInstrumentLoading(false);
      setInstrumentError(null);
      return;
    }
    const key = `${slug}::${ownerFilter ?? ""}::${accountFilter ?? ""}`;
    if (instrumentKeyRef.current !== key) {
      instrumentKeyRef.current = key;
      setInstrumentRows(null);
    }
    let cancelled = false;
    setInstrumentLoading(true);
    setInstrumentError(null);
    loadGroupInstruments(slug, {
      owner: ownerFilter,
      account_type: accountFilter,
    })
      .then((rows) => {
        if (cancelled) return;
        setInstrumentRows(rows);
      })
      .catch((err) => {
        if (cancelled) return;
        setInstrumentError(
          err instanceof Error ? err : new Error(String(err)),
        );
      })
      .finally(() => {
        if (cancelled) return;
        setInstrumentLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [slug, ownerFilter, accountFilter, loadGroupInstruments]);

  useEffect(() => {
    const tickers = portfolio?.accounts?.flatMap((acct) =>
      acct.holdings?.map((h) => h.ticker) ?? [],
    );
    const unique = Array.from(new Set(tickers));
    if (unique.length) {
      preloadInstrumentHistory(unique, 30).catch(() => {});
    }
  }, [portfolio]);

  useEffect(() => {
    if (!slug) return;
    setError(null);
    Promise.all([
      getGroupAlphaVsBenchmark(slug, "VWRL.L"),
      getGroupTrackingError(slug, "VWRL.L"),
      getGroupMaxDrawdown(slug),
    ])
      .then(([a, te, md]) => {
        setAlpha(a.alpha_vs_benchmark);
        setTrackingError(te.tracking_error);
        setMaxDrawdown(md.max_drawdown);
      })
      .catch((e) =>
        setError(e instanceof Error ? e : new Error(String(e)))
      );
  }, [slug]);

  useEffect(() => {
    if (onTradeInfo) {
      onTradeInfo(
        portfolio
          ? {
              as_of: portfolio.as_of,
              trades_this_month: portfolio.trades_this_month,
              trades_remaining: portfolio.trades_remaining,
            }
          : null,
      );
    }
  }, [portfolio, onTradeInfo]);

  const filteredAccounts = useMemo(() => {
    return visibleAccounts.filter((acct) => {
      if (activeOwner && acct.owner !== activeOwner) return false;
      if (activeAccountType && acct.account_type !== activeAccountType) return false;
      return true;
    });
  }, [visibleAccounts, activeOwner, activeAccountType]);

  const totals = useMemo(
    () => computePortfolioTotals(filteredAccounts),
    [filteredAccounts],
  );

  const { ownerRows, typeRows } = useMemo(() => {
    type OwnerAggregate = {
      value: number;
      dayChange: number;
      gain: number;
      cost: number;
      stock: number;
      cash: number;
      accounts: {
        key: string;
        label: string;
        value: number;
        dayChange: number;
        gain: number;
        cost: number;
        stock: number;
        cash: number;
      }[];
    };
    const perOwner: Record<string, OwnerAggregate> = {};
    const perType: Record<string, number> = {};

    for (const acct of filteredAccounts) {
      const owner = acct.owner ?? "—";
      const entry =
        perOwner[owner] ||
        (perOwner[owner] = {
          value: 0,
          dayChange: 0,
          gain: 0,
          cost: 0,
          stock: 0,
          cash: 0,
          accounts: [],
        });

      const accountLabel = acct.account_type
        ? acct.currency
          ? `${acct.account_type} (${acct.currency})`
          : acct.account_type
        : acct.currency ?? "—";

      const accountEntry = {
        key: `${owner}-${entry.accounts.length}`,
        label: accountLabel,
        value: acct.value_estimate_gbp ?? 0,
        dayChange: 0,
        gain: 0,
        cost: 0,
        stock: 0,
        cash: 0,
      };

      entry.accounts.push(accountEntry);

      entry.value += acct.value_estimate_gbp ?? 0;

      for (const h of acct.holdings ?? []) {
        const cost =
          h.cost_basis_gbp && h.cost_basis_gbp > 0
            ? h.cost_basis_gbp
            : h.effective_cost_basis_gbp ?? 0;
        const market = h.market_value_gbp ?? 0;
        const gain =
          h.gain_gbp !== undefined && h.gain_gbp !== null && h.gain_gbp !== 0
            ? h.gain_gbp
            : market - cost;
        const dayChg = h.day_change_gbp ?? 0;

        const typeKey = (h.instrument_type ?? "other").toLowerCase();
        perType[typeKey] = (perType[typeKey] || 0) + market;

        entry.cost += cost;
        entry.gain += gain;
        entry.dayChange += dayChg;
        accountEntry.cost += cost;
        accountEntry.gain += gain;
        accountEntry.dayChange += dayChg;

        const isCash = isCashInstrument({
          instrument_type: h.instrument_type,
          ticker: h.ticker,
        });
        if (isCash) {
          entry.cash += market;
          accountEntry.cash += market;
        } else {
          entry.stock += market;
          accountEntry.stock += market;
        }
      }
    }

    const totalValue = totals.totalValue;

    const ownerRows = Object.entries(perOwner).map(([owner, data]) => {
      const gainPct = data.cost > 0 ? (data.gain / data.cost) * 100 : 0;
      const dayChangePct = computeDayChangePct(data.value, data.dayChange);
      const valuePct = totalValue > 0 ? (data.value / totalValue) * 100 : 0;
      const stockPct = totalValue > 0 ? (data.stock / totalValue) * 100 : 0;
      const cashPct = totalValue > 0 ? (data.cash / totalValue) * 100 : 0;
      const accounts = data.accounts.map((acct) => {
        const accountGainPct = acct.cost > 0 ? (acct.gain / acct.cost) * 100 : 0;
        const accountDayChangePct = computeDayChangePct(acct.value, acct.dayChange);
        const accountValuePct =
          totalValue > 0 ? (acct.value / totalValue) * 100 : 0;
        const accountStockPct =
          totalValue > 0 ? (acct.stock / totalValue) * 100 : 0;
        const accountCashPct =
          totalValue > 0 ? (acct.cash / totalValue) * 100 : 0;
        return {
          ...acct,
          gainPct: accountGainPct,
          dayChangePct: accountDayChangePct,
          valuePct: accountValuePct,
          stockPct: accountStockPct,
          cashPct: accountCashPct,
        };
      });
      const ownerDisplay =
        owner === "—"
          ? "—"
          : getOwnerDisplayName(ownerLookup, owner, owner);
      return {
        owner,
        ownerDisplay,
        ...data,
        gainPct,
        dayChangePct,
        valuePct,
        stockPct,
        cashPct,
        accounts,
      };
    });

    const typeRows = Object.entries(perType).map(([type, value]) => ({
      name: translateInstrumentType(t, type),
      value,
      pct: totalValue > 0 ? (value / totalValue) * 100 : 0,
    }));

    return { ownerRows, typeRows };
  }, [filteredAccounts, t, totals.totalValue, ownerLookup]);

  useEffect(() => {
    setExpandedOwners((prev) => {
      const validOwners = new Set(ownerRows.map((row) => row.owner));
      const filtered = [...prev].filter((owner) => validOwners.has(owner));
      if (filtered.length === prev.size) return prev;
      return new Set(filtered);
    });
  }, [ownerRows]);

  const toggleOwnerExpansion = useCallback((owner: string) => {
    setExpandedOwners((prev) => {
      const next = new Set(prev);
      if (next.has(owner)) {
        next.delete(owner);
      } else {
        next.add(owner);
      }
      return next;
    });
  }, []);

  const handleOwnerSelect = (owner: string | null | undefined) => {
    if (!owner || owner === "—") return;
    if (!props.onSelectMember) return;
    props.onSelectMember(owner);
  };

  /* ── early-return states ───────────────────────────────── */
  if (!slug) return <p>{t("group.select")}</p>;
  if (portfolioError)
    return (
      <p style={{ color: "red" }}>
        {t("common.error")}: {portfolioError.message}
      </p>
    );
  if (loading || !portfolio) return <p>{t("common.loading")}</p>;

  const safeAlpha =
    alpha != null && Math.abs(alpha) > 1 ? alpha / 100 : alpha;
  const safeTrackingError =
    trackingError != null && Math.abs(trackingError) > 1
      ? trackingError / 100
      : trackingError;
  const safeMaxDrawdown =
    maxDrawdown != null && Math.abs(maxDrawdown) > 1
      ? maxDrawdown / 100
      : maxDrawdown;

  const isAllPositions = activeOwner === null;
  const hasFilteredAccounts = filteredAccounts.length > 0;

  /* ── render ────────────────────────────────────────────── */
  return (
    <div style={{ marginTop: "1rem" }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}
      >
        <h2>{getGroupDisplayName(slug, portfolio.name, t)}</h2>
        <RelativeViewToggle />
      </div>

      {!relativeViewEnabled && hasFilteredAccounts && (
        <PortfolioSummary totals={totals} />
      )}

      {isAllPositions && (
        <div
          style={{
            display: "flex",
            gap: "2rem",
            marginBottom: "1rem",
            padding: "0.75rem 1rem",
            backgroundColor: "#222",
            border: "1px solid #444",
            borderRadius: "6px",
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.5rem",
            }}
          >
            <BadgeCheck size={16} />
            <div>
              <div style={{ fontSize: "0.9rem", color: "#aaa" }}>
                Alpha vs Benchmark
              </div>
              <div style={{ fontSize: "1.2rem", fontWeight: "bold" }}>
                {percentOrNa(safeAlpha)}
              </div>
            </div>
          </div>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.5rem",
            }}
          >
            <LineChart size={16} />
            <div>
              <div style={{ fontSize: "0.9rem", color: "#aaa" }}>
                Tracking Error
              </div>
              <div style={{ fontSize: "1.2rem", fontWeight: "bold" }}>
                {percentOrNa(safeTrackingError)}
              </div>
            </div>
          </div>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.5rem",
            }}
          >
            <Shield size={16} />
            <div>
              <div
                style={{ fontSize: "0.9rem", color: "#aaa" }}
                title={t("dashboard.maxDrawdownHelp")}
              >
                {t("dashboard.maxDrawdown")}
              </div>
              <div style={{ fontSize: "1.2rem", fontWeight: "bold" }}>
                {percentOrNa(safeMaxDrawdown)}
              </div>
            </div>
          </div>
        </div>
      )}

      {isAllPositions && (
        <div style={{ marginBottom: "1rem" }}>
          <a
            href="/metrics-explained"
            style={{
              color: "#60a5fa",
              fontSize: "0.85rem",
              textDecoration: "underline",
            }}
          >
            {t("dashboard.metricsExplanationLink")}
          </a>
        </div>
      )}

      {isAllPositions && error && (
        <p style={{ color: "red" }}>
          {t("common.error")}: {error.message}
        </p>
      )}

      {typeRows.length > 0 && (
        <div style={{ width: "100%", height: 240, margin: "1rem 0" }}>
          <ResponsiveContainer>
            <PieChart>
              <Pie
                dataKey="value"
                data={typeRows}
                label={({ name, pct }) => `${name} ${percent(pct)}`}
              >
                {typeRows.map((_, idx) => (
                  <Cell
                    key={`cell-${idx}`}
                    fill={PIE_COLORS[idx % PIE_COLORS.length]}
                  />
                ))}
              </Pie>
              <Tooltip
                formatter={(v: number, n: string) => [
                  money(v, baseCurrency),
                  n,
                ]}
              />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        </div>
      )}

      {isAllPositions && (sectorContrib?.length || regionContrib?.length) && (
        <div style={{ width: "100%", height: 300, margin: "1rem 0" }}>
          <div style={{ marginBottom: "0.5rem" }}>
            <button
              onClick={() => setContribTab("sector")}
              disabled={contribTab === "sector"}
              style={{ marginRight: "0.5rem" }}
            >
              Sector
            </button>
            <button
              onClick={() => setContribTab("region")}
              disabled={contribTab === "region"}
            >
              Region
            </button>
          </div>
          <ResponsiveContainer>
            <BarChart
              data={
                contribTab === "sector"
                  ? sectorContrib || []
                  : regionContrib || []
              }
            >
              <XAxis dataKey={contribTab === "sector" ? "sector" : "region"} />
              <YAxis />
              <Tooltip formatter={(v: number) => money(v, baseCurrency)} />
              <Bar dataKey="gain_gbp">
                {(contribTab === "sector" ? sectorContrib : regionContrib)?.map(
                  (row, idx) => (
                    <Cell
                      key={`cell-bar-${idx}`}
                      fill={row.gain_gbp >= 0 ? "lightgreen" : "red"}
                    />
                  )
                )}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {isAllPositions && <TopMoversSummary slug={slug} />}

      {ownerRows.length > 0 && (
        <table className={tableStyles.table} style={{ marginBottom: "1rem" }}>
          <thead>
            <tr>
              <th className={tableStyles.cell}>Owner</th>
              <th className={`${tableStyles.cell} ${tableStyles.right}`}>
                {relativeViewEnabled ? "Portfolio %" : "Total Value"}
              </th>
              <th className={`${tableStyles.cell} ${tableStyles.right}`}>
                {relativeViewEnabled ? "Stock %" : "Stock Value"}
              </th>
              <th className={`${tableStyles.cell} ${tableStyles.right}`}>
                {relativeViewEnabled ? "Cash %" : "Cash Value"}
              </th>
              {!relativeViewEnabled && (
                <th className={`${tableStyles.cell} ${tableStyles.right}`}>
                  Day Change
                </th>
              )}
              <th className={`${tableStyles.cell} ${tableStyles.right}`}>
                Day Change %
              </th>
              {!relativeViewEnabled && (
                <th className={`${tableStyles.cell} ${tableStyles.right}`}>
                  Total Gain
                </th>
              )}
              <th className={`${tableStyles.cell} ${tableStyles.right}`}>
                Total Gain %
              </th>
            </tr>
          </thead>
          <tbody>
            {ownerRows.map((row) => {
              const hasAccounts = row.accounts.length > 0;
              const isExpanded = hasAccounts && expandedOwners.has(row.owner);
              return (
                <Fragment key={row.owner}>
                  <tr
                    onClick={() => hasAccounts && toggleOwnerExpansion(row.owner)}
                    className={hasAccounts ? tableStyles.clickable : undefined}
                  >
                    <td
                      className={tableStyles.cell}
                      onClick={() => handleOwnerSelect(row.owner)}
                    >
                      {hasAccounts && (
                        <span style={{ marginRight: "0.5rem" }}>
                          {isExpanded ? "▾" : "▸"}
                        </span>
                      )}
                      {row.ownerDisplay}
                    </td>
                  <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                    {relativeViewEnabled
                      ? percent(row.valuePct)
                      : money(row.value, baseCurrency)}
                  </td>
                  <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                    {relativeViewEnabled
                      ? percent(row.stockPct)
                      : money(row.stock, baseCurrency)}
                  </td>
                  <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                    {relativeViewEnabled
                      ? percent(row.cashPct)
                      : money(row.cash, baseCurrency)}
                  </td>
                  {!relativeViewEnabled && (
                    <td
                      className={`${tableStyles.cell} ${tableStyles.right}`}
                      style={{
                        color: row.dayChange >= 0 ? "lightgreen" : "red",
                        }}
                      >
                        {money(row.dayChange, baseCurrency)}
                      </td>
                    )}
                    <td
                      className={`${tableStyles.cell} ${tableStyles.right}`}
                      style={{
                        color: row.dayChange >= 0 ? "lightgreen" : "red",
                      }}
                    >
                      {percent(row.dayChangePct)}
                    </td>
                    {!relativeViewEnabled && (
                      <td
                        className={`${tableStyles.cell} ${tableStyles.right}`}
                        style={{ color: row.gain >= 0 ? "lightgreen" : "red" }}
                      >
                        {money(row.gain, baseCurrency)}
                      </td>
                    )}
                    <td
                      className={`${tableStyles.cell} ${tableStyles.right}`}
                      style={{ color: row.gain >= 0 ? "lightgreen" : "red" }}
                    >
                      {percent(row.gainPct)}
                    </td>
                  </tr>
                  {isExpanded &&
                    row.accounts.map((acct) => (
                      <tr key={acct.key}>
                        <td
                          className={tableStyles.cell}
                          style={{ paddingLeft: "1.75rem", fontSize: "0.9rem" }}
                        >
                          {acct.label}
                        </td>
                    <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                      {relativeViewEnabled
                        ? percent(acct.valuePct)
                        : money(acct.value, baseCurrency)}
                    </td>
                    <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                      {relativeViewEnabled
                        ? percent(acct.stockPct)
                        : money(acct.stock, baseCurrency)}
                    </td>
                    <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                      {relativeViewEnabled
                        ? percent(acct.cashPct)
                        : money(acct.cash, baseCurrency)}
                    </td>
                    {!relativeViewEnabled && (
                      <td
                        className={`${tableStyles.cell} ${tableStyles.right}`}
                        style={{
                          color: acct.dayChange >= 0 ? "lightgreen" : "red",
                            }}
                          >
                            {money(acct.dayChange, baseCurrency)}
                          </td>
                        )}
                        <td
                          className={`${tableStyles.cell} ${tableStyles.right}`}
                          style={{
                            color: acct.dayChange >= 0 ? "lightgreen" : "red",
                          }}
                        >
                          {percent(acct.dayChangePct)}
                        </td>
                        {!relativeViewEnabled && (
                          <td
                            className={`${tableStyles.cell} ${tableStyles.right}`}
                            style={{
                              color: acct.gain >= 0 ? "lightgreen" : "red",
                            }}
                          >
                            {money(acct.gain, baseCurrency)}
                          </td>
                        )}
                        <td
                          className={`${tableStyles.cell} ${tableStyles.right}`}
                          style={{ color: acct.gain >= 0 ? "lightgreen" : "red" }}
                        >
                          {percent(acct.gainPct)}
                        </td>
                      </tr>
                    ))}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      )}

      <div
        role="tablist"
        aria-label="Owners"
        style={{
          display: "flex",
          gap: "0.5rem",
          marginBottom: "1rem",
          flexWrap: "wrap",
        }}
      >
        <button
          type="button"
          role="tab"
          aria-selected={activeOwner === null}
          onClick={() => setActiveOwner(null)}
          style={{
            padding: "0.5rem 0.75rem",
            borderRadius: "4px",
            border: "1px solid #444",
            backgroundColor: activeOwner === null ? "#333" : "transparent",
            color: "inherit",
            cursor: "pointer",
          }}
        >
          All positions
        </button>
        {ownerTabs.map((tab) => (
          <button
            key={tab.value}
            type="button"
            role="tab"
            aria-selected={activeOwner === tab.value}
            onClick={() => setActiveOwner(tab.value)}
            style={{
              padding: "0.5rem 0.75rem",
              borderRadius: "4px",
              border: "1px solid #444",
              backgroundColor:
                activeOwner === tab.value ? "#333" : "transparent",
              color: "inherit",
              cursor: "pointer",
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {activeOwner && (
        <div
          role="tablist"
          aria-label={`${activeOwner} accounts`}
          style={{
            display: "flex",
            gap: "0.5rem",
            marginBottom: "1rem",
            flexWrap: "wrap",
          }}
        >
          <button
            type="button"
            role="tab"
            aria-selected={activeAccountType === null}
            onClick={() => setActiveAccountType(null)}
            style={{
              padding: "0.5rem 0.75rem",
              borderRadius: "4px",
              border: "1px solid #444",
              backgroundColor:
                activeAccountType === null ? "#333" : "transparent",
              color: "inherit",
              cursor: "pointer",
            }}
          >
            All accounts
          </button>
          {ownerTabs
            .find((tab) => tab.value === activeOwner)
            ?.accountTypes.map((type) => (
              <button
                key={type}
                type="button"
                role="tab"
                aria-selected={activeAccountType === type}
                onClick={() => setActiveAccountType(type)}
                style={{
                  padding: "0.5rem 0.75rem",
                  borderRadius: "4px",
                  border: "1px solid #444",
                  backgroundColor:
                    activeAccountType === type ? "#333" : "transparent",
                  color: "inherit",
                  cursor: "pointer",
                }}
              >
                {type}
              </button>
            ))}
        </div>
      )}

      {instrumentError && (
        <p style={{ color: "red" }}>
          {t("common.error")}: {instrumentError.message}
        </p>
      )}
      {instrumentLoading && !instrumentRows && (
        <p>{t("common.loading")}</p>
      )}
      {instrumentRows && (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "flex-start",
            width: "100%",
          }}
        >
          <InstrumentTable rows={instrumentRows} />
        </div>
      )}
    </div>
  );
}

export default GroupPortfolioView;
