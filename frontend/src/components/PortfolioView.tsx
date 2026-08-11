import { Suspense, useState, useEffect, useCallback, useRef } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import type { Portfolio, Account, SectorContribution } from "../types";
import { HoldingsTable } from "./HoldingsTable";
import { InstrumentDetail } from "./InstrumentDetail";
import { AddAccountForm } from "./AddAccountForm";
import { AddPositionForm } from "./AddPositionForm";
import { EmptyState } from "./EmptyState";
import { CsvImportForm } from "./CsvImportForm";
import { ValueAtRisk } from "./ValueAtRisk";
import { money } from "../lib/money";
import { formatDateISO } from "../lib/date";
import { useConfig } from "../ConfigContext";
import { complianceForOwner, getOwnerSectorContributions } from "../api";
import lazyWithDelay from "../utils/lazyWithDelay";
import PortfolioDashboardSkeleton from "./skeletons/PortfolioDashboardSkeleton";
import TextSkeleton from "./skeletons/TextSkeleton";
import { useFetch } from "../hooks/useFetch";
import { aggregateHoldingsByTicker } from "../utils/aggregateHoldings";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Cell,
} from "recharts";

const PerformanceDashboard = lazyWithDelay(
  () => import("@/components/PerformanceDashboard"),
);

const CSV_HEADERS = [
  "owner",
  "as_of",
  "account_type",
  "ticker",
  "name",
  "units",
  "currency",
  "market_value_gbp",
  "gain_gbp",
  "gain_pct",
];

const ADD_POSITION_FORM_ID = "add-position-form";

const sanitizeFilenamePart = (value: string): string =>
  value.replaceAll(/[^a-zA-Z0-9_-]/g, "_");

const escapeCsvCell = (value: string | number | null | undefined): string => {
  const cell = value == null ? "" : String(value);
  const escaped = cell.replaceAll('"', '""');
  return `"${escaped}"`;
};

const buildPortfolioCsv = (portfolio: Portfolio): string => {
  const rows = portfolio.accounts.flatMap((account) =>
    account.holdings.map((holding) => [
      portfolio.owner,
      portfolio.as_of,
      account.account_type,
      holding.ticker,
      holding.name,
      holding.units,
      holding.currency ?? account.currency ?? "",
      holding.market_value_gbp ?? "",
      holding.gain_gbp ?? "",
      holding.gain_pct ?? "",
    ])
  );

  const csvRows = [
    CSV_HEADERS.map(escapeCsvCell).join(","),
    ...rows.map((row) => row.map(escapeCsvCell).join(",")),
  ];

  return `${csvRows.join("\r\n")}\r\n`;
};

const downloadPortfolioCsv = (portfolio: Portfolio): void => {
  const csv = buildPortfolioCsv(portfolio);
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  const safeOwner = sanitizeFilenamePart(portfolio.owner);
  const safeAsOf = sanitizeFilenamePart(portfolio.as_of);
  link.href = url;
  link.download = `${safeOwner}-portfolio-${safeAsOf}.csv`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.setTimeout(() => URL.revokeObjectURL(url), 250);
};

const escapeHtml = (value: string | number | null | undefined): string => {
  const text = value == null ? "" : String(value);
  return text
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
};

const formatNumber = (value: number | null | undefined): string => {
  if (value == null || Number.isNaN(value)) return "";
  return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
};

const buildPortfolioPrintHtml = (portfolio: Portfolio): string => {
  const holdingsRows = portfolio.accounts.flatMap((account) =>
    account.holdings.map((holding) => {
      const cells = [
        account.account_type,
        holding.ticker,
        holding.name,
        formatNumber(holding.units),
        holding.currency ?? account.currency ?? "",
        formatNumber(holding.market_value_gbp),
        formatNumber(holding.gain_gbp),
        formatNumber(holding.gain_pct),
      ];
      const rowHtml = cells.map((cell) => `<td>${escapeHtml(cell)}</td>`).join("");
      return `<tr>${rowHtml}</tr>`;
    })
  );

  const tableBody = holdingsRows.length
    ? holdingsRows.join("")
    : '<tr><td colspan="8">No holdings available.</td></tr>';

  return `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>${escapeHtml(portfolio.owner)} portfolio ${escapeHtml(portfolio.as_of)}</title>
    <style>
      @page { size: A4; margin: 12mm; }
      body { font-family: Inter, Arial, sans-serif; margin: 0; color: #111827; }
      h1 { margin: 0 0 8px; font-size: 20px; }
      p { margin: 0 0 14px; color: #374151; }
      table { width: 100%; border-collapse: collapse; table-layout: fixed; font-size: 11px; }
      th, td { border: 1px solid #d1d5db; padding: 6px; text-align: left; vertical-align: top; word-break: break-word; }
      th { background: #f3f4f6; font-weight: 700; }
    </style>
  </head>
  <body>
    <h1>Portfolio export: ${escapeHtml(portfolio.owner)}</h1>
    <p>As of ${escapeHtml(portfolio.as_of)} • Generated ${escapeHtml(new Date().toLocaleString())}</p>
    <table>
      <thead>
        <tr>
          <th>Account</th>
          <th>Ticker</th>
          <th>Name</th>
          <th>Units</th>
          <th>Currency</th>
          <th>Market Value (GBP)</th>
          <th>Gain (GBP)</th>
          <th>Gain %</th>
        </tr>
      </thead>
      <tbody>${tableBody}</tbody>
    </table>
  </body>
</html>`;
};

const printPortfolioPdf = (portfolio: Portfolio): void => {
  const iframe = document.createElement("iframe");
  iframe.style.position = "fixed";
  iframe.style.right = "0";
  iframe.style.bottom = "0";
  iframe.style.width = "0";
  iframe.style.height = "0";
  iframe.style.border = "0";
  iframe.setAttribute("aria-hidden", "true");
  document.body.appendChild(iframe);

  const cleanup = () => {
    iframe.onload = null;
    if (document.body.contains(iframe)) {
      document.body.removeChild(iframe);
    }
  };

  iframe.onload = () => {
    const printContext = iframe.contentWindow;
    if (!printContext) {
      cleanup();
      return;
    }
    printContext.focus();
    printContext.print();
    window.setTimeout(cleanup, 1200);
  };

  const frameDocument = iframe.contentDocument ?? iframe.contentWindow?.document;
  if (!frameDocument) {
    cleanup();
    return;
  }
  frameDocument.open();
  frameDocument.write(buildPortfolioPrintHtml(portfolio));
  frameDocument.close();
};

// Props accepted by the view. `data` is null until a portfolio is loaded.
type Props = {
  data: Portfolio | null;
  loading?: boolean;
  error?: string | null;
  onDateChange?: (isoDate: string | null) => void;
  onAccountAdded?: () => void;
  onPositionAdded?: () => void;
};

/**
 * Render a portfolio tree showing an owner's accounts and holdings.
 *
 * The component is intentionally tiny: it deals only with presentation and
 * relies on its parent for data fetching. Conditional branches early-return to
 * keep the JSX at the bottom easy to follow.
 */
export function PortfolioView({ data, loading, error, onDateChange, onAccountAdded, onPositionAdded }: Props) {
  const { t } = useTranslation();
  const [activeAccount, setActiveAccount] = useState("all");
  const [selectedInstrument, setSelectedInstrument] = useState<{
    ticker: string;
    name: string;
  } | null>(null);
  const [hasWarnings, setHasWarnings] = useState(false);
  const [pendingDate, setPendingDate] = useState<string>("");
  const [showAddAccount, setShowAddAccount] = useState(false);
  const [showCsvImport, setShowCsvImport] = useState(false);
  const [addPositionAccount, setAddPositionAccount] = useState<string | undefined>(undefined);
  const [addPositionExpanded, setAddPositionExpanded] = useState(false);
  const addPositionRef = useRef<HTMLDivElement>(null);
  const { baseCurrency, familyMvpEnabled, enableAdvancedAnalytics = true } = useConfig();

  const accountKey = (acct: Account, idx: number) => `${acct.account_type}-${idx}`;

  const lastOwnerRef = useRef<string | null>(null);

  useEffect(() => {
    const owner = data?.owner ?? null;
    if (owner !== lastOwnerRef.current) {
      lastOwnerRef.current = owner;
      setActiveAccount("all");
      return;
    }
    if (
      activeAccount !== "all" &&
      !data?.accounts.some((account, index) => accountKey(account, index) === activeAccount)
    ) {
      setActiveAccount("all");
    }
  }, [activeAccount, data]);

  useEffect(() => {
    setPendingDate(data?.as_of ?? "");
  }, [data?.as_of]);

  const handleAddPositionCollapse = useCallback(() => {
    setAddPositionExpanded(false);
    setAddPositionAccount(undefined);
  }, []);

  useEffect(() => {
    if (!addPositionExpanded) return;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") handleAddPositionCollapse();
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [addPositionExpanded, handleAddPositionCollapse]);

  const owner = data?.owner ?? null;
  const asOf = data?.as_of ?? null;

  const fetchSectorContribution = useCallback(() => {
    if (!owner || !enableAdvancedAnalytics) return Promise.resolve([] as SectorContribution[]);
    return getOwnerSectorContributions(owner, { asOf: asOf ?? undefined });
  }, [owner, asOf, enableAdvancedAnalytics]);

  const {
    data: sectorContrib,
    loading: sectorLoading,
    error: sectorError,
  } = useFetch<SectorContribution[]>(
    fetchSectorContribution,
    [owner, asOf, enableAdvancedAnalytics],
    Boolean(owner && enableAdvancedAnalytics),
  );

  useEffect(() => {
    let cancelled = false;
    async function check() {
      if (!owner) {
        setHasWarnings(false);
        return;
      }
      try {
        const res = await complianceForOwner(owner);
        if (!cancelled) setHasWarnings(res.warnings.length > 0);
      } catch {
        if (!cancelled) setHasWarnings(false);
      }
    }
    check();
    return () => {
      cancelled = true;
    };
  }, [owner]);

  if (loading) return <PortfolioDashboardSkeleton label={t("app.loading")} />;
  if (error) return <div className="text-error">{error}</div>; // bubble errors
  if (!data) return <div>Select an owner.</div>; // nothing chosen yet

  const activeAccountIndex = data.accounts.findIndex(
    (account, index) => accountKey(account, index) === activeAccount,
  );
  const scopedAccounts =
    activeAccount === "all" || activeAccountIndex < 0
      ? data.accounts
      : [data.accounts[activeAccountIndex]];
  const totalValue = scopedAccounts.reduce(
    (sum, account) => sum + account.value_estimate_gbp,
    0,
  );
  const accountHoldings = scopedAccounts.flatMap((account) => {
    const originalIndex = data.accounts.indexOf(account);
    const sourceKey = accountKey(account, originalIndex);
    return account.holdings.map((holding, holdingIndex) => ({
      ...holding,
      source_account: account.account_type,
      row_key: `${sourceKey}-${holdingIndex}`,
    }));
  });
  const scopedHoldings =
    activeAccount === "all"
      ? aggregateHoldingsByTicker(accountHoldings, data.as_of)
      : accountHoldings;

  const asOfDate = data.as_of ? new Date(data.as_of) : null;
  const todayIso = formatDateISO(new Date());
  const daysSince = asOfDate
    ? Math.floor((Date.now() - asOfDate.getTime()) / (1000 * 60 * 60 * 24))
    : 0;
  const showForward7d = daysSince >= 7;
  const showForward30d = daysSince >= 30;

  const handleDateSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmed = pendingDate.trim();
    onDateChange?.(trimmed ? trimmed : null);
  };

  const handleExportCsv = () => {
    if (!data) return;
    downloadPortfolioCsv(data);
  };

  const handleExportPdf = () => {
    if (!data) return;
    printPortfolioPdf(data);
  };

  const handleAccountCreated = () => {
    setShowAddAccount(false);
    onAccountAdded?.();
  };

  const handleAddPositionRequest = (accountType?: string) => {
    setAddPositionAccount(accountType);
    setAddPositionExpanded(true);
    addPositionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const handlePositionAdded = () => {
    setAddPositionExpanded(false);
    setAddPositionAccount(undefined);
    onPositionAdded?.();
  };

  const handleCsvImported = () => {
    setShowCsvImport(false);
    onPositionAdded?.();
  };

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-6">
        <section className="rounded-lg border border-gray-800 bg-gray-900/70 p-4 md:p-6">
          {!familyMvpEnabled && (
            <form
              onSubmit={handleDateSubmit}
              className="mb-4 flex flex-wrap items-center gap-2 text-sm text-gray-300"
            >
              <label htmlFor="portfolio-as-of" className="flex items-center gap-2">
                <span>As of</span>
                <input
                  id="portfolio-as-of"
                  type="date"
                  value={pendingDate}
                  max={todayIso}
                  onChange={(e) => setPendingDate(e.target.value)}
                  className="rounded border border-gray-700 bg-gray-800 p-1 text-white"
                />
              </label>
              <button
                type="submit"
                className="rounded bg-blue-600 px-3 py-1 text-white hover:bg-blue-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-400"
              >
                Go
              </button>
              {data.as_of && (
                <span className="text-xs text-gray-400">
                  Showing {formatDateISO(new Date(data.as_of))}
                </span>
              )}
            </form>
          )}
          <div className="mb-6 text-lg font-semibold text-white">
            Approx Total: {money(totalValue, baseCurrency)}
          </div>
          {data.accounts.length > 0 && (
            <div className="mb-6 flex flex-wrap items-center gap-2">
              {!familyMvpEnabled && (
                <>
                  <button
                    type="button"
                    onClick={handleExportCsv}
                    aria-label="Export portfolio as CSV"
                    className="rounded border border-gray-700 px-3 py-1.5 text-sm text-white hover:border-gray-500 hover:bg-gray-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-400"
                  >
                    Export CSV
                  </button>
                  <button
                    type="button"
                    onClick={handleExportPdf}
                    aria-label="Export portfolio as PDF"
                    className="rounded border border-gray-700 px-3 py-1.5 text-sm text-white hover:border-gray-500 hover:bg-gray-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-400"
                  >
                    Export PDF
                  </button>
                </>
              )}
              {!addPositionExpanded && (
                <button
                  type="button"
                  onClick={() =>
                    handleAddPositionRequest(
                      activeAccountIndex >= 0
                        ? data.accounts[activeAccountIndex].account_type
                        : undefined,
                    )
                  }
                  aria-expanded="false"
                  aria-controls={ADD_POSITION_FORM_ID}
                  className="rounded border border-gray-700 px-3 py-1.5 text-sm text-white hover:border-gray-500 hover:bg-gray-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-400"
                >
                  + {t("addPosition.title")}
                </button>
              )}
              {!showCsvImport && (
                <button
                  type="button"
                  onClick={() => setShowCsvImport(true)}
                  className="rounded border border-gray-700 px-3 py-1.5 text-sm text-white hover:border-gray-500 hover:bg-gray-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-400"
                >
                  + Import CSV
                </button>
              )}
              {!showAddAccount && (
                <button
                  type="button"
                  onClick={() => setShowAddAccount(true)}
                  className="rounded border border-gray-700 px-3 py-1.5 text-sm text-white hover:border-gray-500 hover:bg-gray-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-400"
                >
                  Add account
                </button>
              )}
            </div>
          )}
          <div ref={addPositionRef}>
            {addPositionExpanded && (
              <div className="mb-6">
                <AddPositionForm
                  owner={data.owner}
                  accounts={data.accounts.map((acct) => acct.account_type)}
                  defaultAccount={addPositionAccount}
                  onAdded={handlePositionAdded}
                  onCollapse={handleAddPositionCollapse}
                  controlsId={ADD_POSITION_FORM_ID}
                />
              </div>
            )}
          </div>
          {showCsvImport && data.accounts.length > 0 && (
            <div className="mb-6">
              <CsvImportForm
                owner={data.owner}
                accountTypes={data.accounts.map((acct) => acct.account_type)}
                onImported={handleCsvImported}
              />
              <button
                type="button"
                onClick={() => setShowCsvImport(false)}
                className="mt-2 text-xs text-gray-400 underline hover:text-white"
              >
                Cancel import
              </button>
            </div>
          )}
          {showAddAccount && (
            <div className="mb-6">
              <AddAccountForm
                owner={data.owner}
                onCreated={handleAccountCreated}
                onCancel={() => setShowAddAccount(false)}
              />
            </div>
          )}
          {hasWarnings && (
            <div className="mb-4">
              <Link
                to={`/compliance/${data.owner}`}
                className="text-blue-400 hover:text-blue-300"
              >
                View compliance warnings
              </Link>
            </div>
          )}
          {enableAdvancedAnalytics && (
            <>
              <div className="mb-6 rounded-lg border border-gray-800 bg-black/30 p-4">
                <ValueAtRisk owner={data.owner} onDateChange={onDateChange} />
              </div>
              {!familyMvpEnabled && (
                <div className="mb-6 rounded-lg border border-gray-800 bg-black/30 p-4">
                  <h3 className="mb-3 text-base font-semibold text-white">
                    Sector contribution
                  </h3>
                  {sectorLoading ? (
                    <TextSkeleton width="8rem" label={t("app.loading")} />
                  ) : sectorError ? (
                    <p className="text-sm text-red-500">
                      Failed to load sector contribution
                    </p>
                  ) : sectorContrib && sectorContrib.length > 0 ? (
                    <div className="h-64 w-full">
                      <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}>
                        <BarChart data={sectorContrib}>
                          <XAxis dataKey="sector" interval={0} angle={-35} textAnchor="end" height={70} />
                          <YAxis />
                          <Tooltip formatter={(v) => money(v as number | undefined, baseCurrency)} />
                          <Bar dataKey="gain_gbp">
                            {sectorContrib.map((row, idx) => (
                              <Cell
                                key={`${row.sector}-${idx}`}
                                fill={row.gain_gbp >= 0 ? "#22c55e" : "#ef4444"}
                              />
                            ))}
                          </Bar>
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  ) : (
                    <p className="text-sm text-gray-400">No sector data available.</p>
                  )}
                </div>
              )}
            </>
          )}
          {data.accounts.length > 0 && (
            <section aria-label="Portfolio holdings" className="min-w-0">
              <div
                role="tablist"
                aria-label="Portfolio accounts"
                className="mb-4 flex max-w-full gap-1 overflow-x-auto border-b border-gray-700"
              >
                {[
                  { key: "all", label: "All accounts" },
                  ...data.accounts.map((account, index) => ({
                    key: accountKey(account, index),
                    label: account.account_type,
                  })),
                ].map((tab) => (
                  <button
                    key={tab.key}
                    type="button"
                    role="tab"
                    aria-selected={activeAccount === tab.key}
                    onClick={() => setActiveAccount(tab.key)}
                    className={`shrink-0 border-b-2 px-3 py-2 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-400 ${
                      activeAccount === tab.key
                        ? "border-blue-400 font-semibold text-white"
                        : "border-transparent text-gray-400 hover:text-white"
                    }`}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>
              <HoldingsTable
                holdings={scopedHoldings}
                showAccount={false}
                onSelectInstrument={(ticker, name) =>
                  setSelectedInstrument({ ticker, name })
                }
                selectedTicker={selectedInstrument?.ticker}
                showForward7d={showForward7d}
                showForward30d={showForward30d}
                onAddPosition={() =>
                  handleAddPositionRequest(
                    activeAccountIndex >= 0
                      ? data.accounts[activeAccountIndex].account_type
                      : undefined,
                  )
                }
              />
              {selectedInstrument && (
                <InstrumentDetail
                  ticker={selectedInstrument.ticker}
                  name={selectedInstrument.name}
                  onClose={() => setSelectedInstrument(null)}
                />
              )}
            </section>
          )}
          {data.accounts.length === 0 && (
            <div className="mb-6 mt-4">
              <EmptyState
                message="Get started by adding your first account (e.g. ISA, SIPP, brokerage or savings)."
                actions={[
                  { label: "Add account", onClick: () => setShowAddAccount(true) },
                ]}
              />
            </div>
          )}
        </section>
        {enableAdvancedAnalytics && (
          <section className="rounded-lg border border-gray-800 bg-gray-900/70 p-4 md:p-6">
            <Suspense fallback={<PortfolioDashboardSkeleton />}>
              <PerformanceDashboard owner={data.owner} asOf={data.as_of} />
            </Suspense>
          </section>
        )}
      </div>
    </div>
  );
}
