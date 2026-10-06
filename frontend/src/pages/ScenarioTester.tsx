import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import {
  getEvents,
  getOwners,
  getPortfolio,
  runScenario,
} from "../api";
import type {
  OwnerSummary,
  Portfolio,
  ScenarioEvent,
  ScenarioResult,
  SyntheticHolding,
} from "../types";
import {
  createOwnerDisplayLookup,
  getOwnerDisplayName,
  sanitizeOwners,
} from "../utils/owners";
import errorToast from "../utils/errorToast";
import { loadJSON, saveJSON } from "../utils/storage";
import { MAX_SCENARIO_HOLDING_ROWS } from "../constants/renderLimits";
import { useDedupedRequest } from "../hooks/useDedupedRequest";
import { money } from "../lib/money";
import { FxShockPanel } from "../components/FxShockPanel";

const HORIZONS = ["1d", "1w", "1m", "3m", "1y"];

type PortfolioState = {
  status: "idle" | "loading" | "ready" | "error";
  asOf: string | null;
  data?: Portfolio;
  error?: string;
};

type ScenarioHoldingRow = {
  key: string;
  ticker: string;
  name: string;
  units: number;
  marketValue: number | null;
  owners: string[];
  source: "existing" | "custom";
  currency?: string | null;
  customIndex?: number;
  isRemoved?: boolean;
};

type CustomHolding = SyntheticHolding & { name?: string };

const SUGGESTED_DATES: { date: string; labelKey: string }[] = [
  { date: "2020-03-16", labelKey: "scenarioTester.suggested.covid" },
  { date: "2022-09-26", labelKey: "scenarioTester.suggested.giltCrisis" },
  { date: "2022-03-08", labelKey: "scenarioTester.suggested.energyShock" },
  { date: "2023-03-13", labelKey: "scenarioTester.suggested.bankingTurmoil" },
];

export default function ScenarioTester() {
  const { t } = useTranslation();
  const [events, setEvents] = useState<ScenarioEvent[]>([]);
  const [owners, setOwners] = useState<OwnerSummary[]>([]);
  const [portfolioStates, setPortfolioStates] = useState<Record<string, PortfolioState>>({});
  const [eventId, setEventId] = useState("");
  const [horizons, setHorizons] = useState<string[]>([]);
  const [results, setResults] = useState<ScenarioResult[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ownerError, setOwnerError] = useState<string | null>(null);
  const [selectedOwners, setSelectedOwners] = useState<string[]>(() =>
    loadJSON<string[]>("scenario.selectedOwners", []),
  );
  const [reportingDate, setReportingDate] = useState<string>(() =>
    loadJSON<string>("scenario.reportingDate", ""),
  );
  const [customHoldings, setCustomHoldings] = useState<CustomHolding[]>(() =>
    loadJSON<CustomHolding[]>("scenario.customHoldings", []),
  );
  const [removedKeys, setRemovedKeys] = useState<Set<string>>(() => new Set());

  // Market values and scenario results are GBP amounts; money() labels them,
  // it does not convert, so they stay labelled GBP (#9725).
  const fmt = { format: (v: number) => money(v, "GBP") };

  useEffect(() => {
    getEvents()
      .then(setEvents)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  useEffect(() => {
    getOwners()
      .then((data) => setOwners(sanitizeOwners(data)))
      .catch((e) => {
        const msg = e instanceof Error ? e.message : String(e);
        setOwnerError(msg);
        errorToast(e);
      });
  }, []);

  useEffect(() => {
    saveJSON("scenario.selectedOwners", selectedOwners);
  }, [selectedOwners]);

  useEffect(() => {
    saveJSON("scenario.reportingDate", reportingDate);
  }, [reportingDate]);

  useEffect(() => {
    saveJSON("scenario.customHoldings", customHoldings);
  }, [customHoldings]);

  const ownerLookup = useMemo(
    () => createOwnerDisplayLookup(owners),
    [owners],
  );

  const effectiveDate = reportingDate.trim() === "" ? null : reportingDate.trim();

  const { run: runPortfolioRequest, clear: clearPortfolioRequests } =
    useDedupedRequest<Portfolio>();

  const ensurePortfolioLoaded = useCallback(
    (owner: string) => {
      const requestKey = `${owner}::${effectiveDate ?? ""}`;

      setPortfolioStates((prev) => ({
        ...prev,
        [owner]: { status: "loading", asOf: effectiveDate ?? null },
      }));

      // The dedupe key is owner+date, but the request itself must receive the
      // bare owner; passing the key through produced /portfolio/{owner}:: (#8576).
      runPortfolioRequest(requestKey, () =>
        getPortfolio(owner, { asOf: effectiveDate }),
      )
        .then((pf) => {
          if (pf === undefined) {
            return;
          }
          setPortfolioStates((prev) => {
            const state = prev[owner];
            if (!state || state.asOf !== (effectiveDate ?? null)) {
              return prev;
            }
            return {
              ...prev,
              [owner]: {
                status: "ready",
                asOf: effectiveDate ?? null,
                data: pf,
              },
            };
          });
        })
        .catch((e) => {
          const msg = e instanceof Error ? e.message : String(e);
          setPortfolioStates((prev) => {
            const state = prev[owner];
            if (!state || state.asOf !== (effectiveDate ?? null)) {
              return prev;
            }
            return {
              ...prev,
              [owner]: {
                status: "error",
                asOf: effectiveDate ?? null,
                error: msg,
              },
            };
          });
        });
    },
    [effectiveDate, runPortfolioRequest],
  );

  useEffect(() => {
    if (selectedOwners.length === 0) return;
    selectedOwners.forEach((owner) => ensurePortfolioLoaded(owner));
  }, [selectedOwners, ensurePortfolioLoaded]);

  useEffect(() => {
    clearPortfolioRequests();
    setPortfolioStates({});
  }, [effectiveDate, clearPortfolioRequests]);

  const toggleHorizon = (h: string) => {
    setHorizons((prev) =>
      prev.includes(h) ? prev.filter((x) => x !== h) : [...prev, h],
    );
  };

  const canRun = eventId !== "" && horizons.length > 0;

  async function handleRun() {
    setError(null);
    try {
      const data = await runScenario({ event_id: eventId, horizons });
      setResults(data);
    } catch (e) {
      setResults(null);
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  const combinedHoldings: ScenarioHoldingRow[] = useMemo(() => {
    const aggregated = new Map<string, ScenarioHoldingRow>();
    selectedOwners.forEach((owner) => {
      const state = portfolioStates[owner];
      if (state?.status !== "ready" || !state.data) return;
      state.data.accounts.forEach((acct) => {
        acct.holdings.forEach((h) => {
          const rawTicker = (h.ticker || "").trim();
          const key = rawTicker
            ? rawTicker.toUpperCase()
            : `${owner}:${acct.account_type}:${h.name ?? ""}`;
          const existing = aggregated.get(key);
          const units = Number(h.units ?? 0);
          const mv =
            h.market_value_gbp != null ? Number(h.market_value_gbp) : null;
          if (existing) {
            existing.units += units;
            if (mv != null) {
              existing.marketValue = (existing.marketValue ?? 0) + mv;
            }
            if (!existing.owners.includes(owner)) {
              existing.owners = [...existing.owners, owner];
            }
          } else {
            aggregated.set(key, {
              key,
              ticker: rawTicker ? rawTicker.toUpperCase() : h.name ?? key,
              name: (h.name ?? rawTicker) || t("scenarioTester.unnamedHolding"),
              units,
              marketValue: mv,
              owners: [owner],
              source: "existing",
              currency: h.market_value_currency ?? h.currency ?? null,
            });
          }
        });
      });
    });

    const existingRows = Array.from(aggregated.values()).map((row) => ({
      ...row,
      isRemoved: removedKeys.has(row.key),
    }));

    const customs = customHoldings.map((holding, idx) => {
      const units = Number(holding.units ?? 0);
      const price =
        holding.price != null ? Number(holding.price) : undefined;
      const marketValue =
        price != null && Number.isFinite(price) ? price * units : null;
      const ticker = (holding.ticker || "").trim();
      return {
        key: `custom-${idx}`,
        ticker: ticker ? ticker.toUpperCase() : t("scenarioTester.customTicker", { index: idx + 1 }),
        name: holding.ticker || holding.name || t("scenarioTester.customPositionName", { index: idx + 1 }),
        units,
        marketValue: marketValue != null ? Number(marketValue) : null,
        owners: ["Custom"],
        source: "custom" as const,
        currency: undefined,
        customIndex: idx,
        isRemoved: false,
      } satisfies ScenarioHoldingRow;
    });

    return [...existingRows, ...customs].sort((a, b) =>
      a.ticker.localeCompare(b.ticker),
    );
  }, [selectedOwners, portfolioStates, removedKeys, customHoldings, t]);

  const activeHoldings = useMemo(
    () =>
      combinedHoldings.filter(
        (row) => row.source === "custom" || !row.isRemoved,
      ),
    [combinedHoldings],
  );

  const totalMarketValue = useMemo(() => {
    return activeHoldings.reduce((sum, row) => {
      const mv = row.marketValue;
      return mv != null ? sum + mv : sum;
    }, 0);
  }, [activeHoldings]);

  const visibleCombinedHoldings = useMemo(
    () => combinedHoldings.slice(0, MAX_SCENARIO_HOLDING_ROWS),
    [combinedHoldings],
  );

  function toggleHoldingRemoval(key: string) {
    setRemovedKeys((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  }

  function resetRemovals() {
    setRemovedKeys(new Set());
  }

  function handleAddCustomHolding() {
    setCustomHoldings((prev) => [
      ...prev,
      { ticker: "", units: 0, price: undefined, name: "" },
    ]);
  }

  function updateCustomHolding(
    index: number,
    field: keyof CustomHolding,
    value: string,
  ) {
    setCustomHoldings((prev) =>
      prev.map((item, idx) =>
        idx === index
          ? {
              ...item,
              [field]: (() => {
                if (field === "units") {
                  const parsed = Number(value);
                  return Number.isFinite(parsed) ? parsed : 0;
                }
                if (field === "price") {
                  if (value.trim() === "") {
                    return undefined;
                  }
                  const parsed = Number(value);
                  return Number.isFinite(parsed) ? parsed : item.price;
                }
                return value;
              })(),
            }
          : item,
      ),
    );
  }

  function removeCustomHolding(index: number) {
    setCustomHoldings((prev) => prev.filter((_, idx) => idx !== index));
  }

  function clearCustomHoldings() {
    setCustomHoldings([]);
  }

  function handleSelectAllOwners() {
    setSelectedOwners(owners.map((o) => o.owner));
  }

  function handleClearOwners() {
    setSelectedOwners([]);
  }

  function handleToggleOwner(owner: string) {
    setSelectedOwners((prev) =>
      prev.includes(owner)
        ? prev.filter((o) => o !== owner)
        : [...prev, owner],
    );
  }

  function handleSuggestedDate(date: string) {
    setReportingDate(date);
  }

  function clearReportingDate() {
    setReportingDate("");
  }

  function downloadScenario() {
    if (activeHoldings.length === 0) {
      return;
    }
    const payload = {
      generated_at: new Date().toISOString(),
      reporting_date: effectiveDate,
      owners: selectedOwners,
      holdings: activeHoldings.map((row) => ({
        ticker: row.ticker,
        name: row.name,
        units: row.units,
        market_value_gbp: row.marketValue,
        currency: row.currency ?? "GBP",
        source: row.source,
        owners: row.owners,
      })),
      totals: {
        market_value_gbp: Number(totalMarketValue.toFixed(2)),
      },
    };

    try {
      const blob = new Blob([JSON.stringify(payload, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      const datePart = effectiveDate ?? new Date().toISOString().slice(0, 10);
      anchor.download = `scenario-${datePart}.json`;
      document.body.appendChild(anchor);
      anchor.click();
      document.body.removeChild(anchor);
      URL.revokeObjectURL(url);
    } catch (e) {
      errorToast(e);
    }
  }

  const ownersLoaded = owners.length > 0;

  return (
    <div className="container mx-auto flex flex-col gap-6 p-4">
      <section className="rounded-md border border-slate-200 bg-white p-4 text-slate-900 shadow-sm">
        <header className="mb-3 flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
          <h1 className="text-xl font-semibold">{t("scenarioTester.title")}</h1>
          <div className="flex flex-wrap gap-2">
            <button
              className="rounded border border-slate-300 px-3 py-1 text-sm hover:bg-slate-100"
              type="button"
              onClick={handleSelectAllOwners}
              disabled={!ownersLoaded}
            >
              {t("scenarioTester.selectAll")}
            </button>
            <button
              className="rounded border border-slate-300 px-3 py-1 text-sm hover:bg-slate-100"
              type="button"
              onClick={handleClearOwners}
              disabled={selectedOwners.length === 0}
            >
              {t("scenarioTester.clearSelection")}
            </button>
          </div>
        </header>
        {ownerError && (
          <p className="mb-3 rounded border border-red-200 bg-red-50 p-2 text-sm text-red-700">
            {ownerError}
          </p>
        )}
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {owners.map((owner) => {
            const state = portfolioStates[owner.owner];
            const statusLabel = (() => {
              if (!selectedOwners.includes(owner.owner)) return null;
              if (!state) return "";
              if (state.status === "loading") return t("scenarioTester.loading");
              if (state.status === "error") return state.error;
              return t("scenarioTester.loaded");
            })();
            return (
              <label
                key={owner.owner}
                className="flex flex-col gap-1 rounded border border-slate-200 p-3 hover:border-slate-400"
              >
                <span className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={selectedOwners.includes(owner.owner)}
                    onChange={() => handleToggleOwner(owner.owner)}
                  />
                  <span className="font-medium">
                    {getOwnerDisplayName(ownerLookup, owner.owner)}
                  </span>
                </span>
                {statusLabel ? (
                  <span className="text-xs text-slate-500">{statusLabel}</span>
                ) : null}
                <span className="text-xs text-slate-500">
                  {t("scenarioTester.accounts", { count: owner.accounts?.length ?? 0 })}
                </span>
              </label>
            );
          })}
          {owners.length === 0 && !ownerError && (
            <p className="text-sm text-slate-500">{t("scenarioTester.loadingPortfolios")}</p>
          )}
        </div>
      </section>

      <section className="rounded-md border border-slate-200 bg-white p-4 text-slate-900 shadow-sm">
        <h2 className="mb-3 text-lg font-semibold">{t("scenarioTester.reportingDate")}</h2>
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:gap-4">
          <label className="flex items-center gap-2 text-sm">
            <span>{t("scenarioTester.date")}</span>
            <input
              type="date"
              value={reportingDate}
              onChange={(e) => setReportingDate(e.target.value)}
              className="rounded border border-slate-300 px-2 py-1"
            />
          </label>
          <button
            type="button"
            onClick={clearReportingDate}
            className="w-fit rounded border border-slate-300 px-3 py-1 text-sm hover:bg-slate-100"
            disabled={reportingDate.trim() === ""}
          >
            {t("scenarioTester.useLatest")}
          </button>
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          {SUGGESTED_DATES.map((item) => (
            <button
              key={item.date}
              type="button"
              onClick={() => handleSuggestedDate(item.date)}
              className={`rounded px-3 py-1 text-sm shadow-sm transition-colors ${
                reportingDate === item.date
                  ? "bg-indigo-600 text-white"
                  : "bg-slate-100 text-slate-700 hover:bg-slate-200"
              }`}
            >
              {t(item.labelKey)} ({item.date})
            </button>
          ))}
        </div>
      </section>

      <section className="rounded-md border border-slate-200 bg-white p-4 text-slate-900 shadow-sm">
        <div className="mb-3 flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
          <h2 className="text-lg font-semibold">{t("scenarioTester.positions")}</h2>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={resetRemovals}
              className="rounded border border-slate-300 px-3 py-1 text-sm hover:bg-slate-100"
              disabled={removedKeys.size === 0}
            >
              {t("scenarioTester.restoreRemoved")}
            </button>
            <button
              type="button"
              onClick={handleAddCustomHolding}
              className="rounded border border-indigo-500 px-3 py-1 text-sm text-indigo-600 hover:bg-indigo-50"
            >
              {t("scenarioTester.addCustom")}
            </button>
            <button
              type="button"
              onClick={clearCustomHoldings}
              className="rounded border border-slate-300 px-3 py-1 text-sm hover:bg-slate-100"
              disabled={customHoldings.length === 0}
            >
              {t("scenarioTester.removeCustom")}
            </button>
          </div>
        </div>

        {selectedOwners.length === 0 && customHoldings.length === 0 ? (
          <p className="text-sm text-slate-500">
            {t("scenarioTester.emptyState")}
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full border border-slate-200 text-sm">
              <thead className="bg-slate-50">
                <tr>
                  <th className="p-2 text-left">{t("scenarioTester.columns.ticker")}</th>
                  <th className="p-2 text-left">{t("scenarioTester.columns.name")}</th>
                  <th className="p-2 text-right">{t("scenarioTester.columns.units")}</th>
                  <th className="p-2 text-right">{t("scenarioTester.columns.marketValue")}</th>
                  <th className="p-2 text-left">{t("scenarioTester.columns.source")}</th>
                  <th className="p-2 text-left">{t("scenarioTester.columns.owners")}</th>
                  <th className="p-2 text-right">{t("scenarioTester.columns.actions")}</th>
                </tr>
              </thead>
              <tbody>
                {visibleCombinedHoldings.map((row) => {
                  if (row.source === "custom") {
                    return (
                      <tr key={row.key} className="border-t">
                        <td className="p-2 align-top">
                          <input
                            type="text"
                            value={customHoldings[row.customIndex ?? 0]?.ticker ?? ""}
                            onChange={(e) =>
                              updateCustomHolding(
                                row.customIndex ?? 0,
                                "ticker",
                                e.target.value,
                              )
                            }
                            className="w-24 rounded border border-slate-300 px-2 py-1"
                          />
                        </td>
                        <td className="p-2 align-top">
                          <input
                            type="text"
                            value={customHoldings[row.customIndex ?? 0]?.name ?? ""}
                            onChange={(e) =>
                              updateCustomHolding(
                                row.customIndex ?? 0,
                                "name",
                                e.target.value,
                              )
                            }
                            className="w-40 rounded border border-slate-300 px-2 py-1"
                          />
                        </td>
                        <td className="p-2 text-right align-top">
                          <input
                            type="number"
                            value={customHoldings[row.customIndex ?? 0]?.units ?? 0}
                            onChange={(e) =>
                              updateCustomHolding(
                                row.customIndex ?? 0,
                                "units",
                                e.target.value,
                              )
                            }
                            className="w-24 rounded border border-slate-300 px-2 py-1 text-right"
                          />
                        </td>
                        <td className="p-2 text-right align-top">
                          <input
                            type="number"
                            value={customHoldings[row.customIndex ?? 0]?.price ?? ""}
                            onChange={(e) =>
                              updateCustomHolding(
                                row.customIndex ?? 0,
                                "price",
                                e.target.value,
                              )
                            }
                            className="w-24 rounded border border-slate-300 px-2 py-1 text-right"
                            placeholder={t("scenarioTester.pricePlaceholder")}
                          />
                        </td>
                        <td className="p-2 align-top">{t("scenarioTester.source.custom")}</td>
                        <td className="p-2 align-top">—</td>
                        <td className="p-2 text-right align-top">
                          <button
                            type="button"
                            onClick={() => removeCustomHolding(row.customIndex ?? 0)}
                            className="rounded border border-red-300 px-2 py-1 text-xs text-red-600 hover:bg-red-50"
                          >
                            {t("scenarioTester.remove")}
                          </button>
                        </td>
                      </tr>
                    );
                  }

                  return (
                    <tr
                      key={row.key}
                      className={`border-t ${
                        row.isRemoved ? "bg-red-50 text-slate-500" : ""
                      }`}
                    >
                      <td className="p-2 align-top font-mono text-sm">{row.ticker}</td>
                      <td className="p-2 align-top">{row.name}</td>
                      <td className="p-2 text-right align-top">
                        {row.units.toLocaleString(undefined, {
                          maximumFractionDigits: 2,
                        })}
                      </td>
                      <td className="p-2 text-right align-top">
                        {row.marketValue != null
                          ? fmt.format(row.marketValue)
                          : "—"}
                      </td>
                      <td className="p-2 align-top capitalize">{t(`scenarioTester.source.${row.source}`)}</td>
                      <td className="p-2 align-top text-xs text-slate-600">
                        {row.owners
                          .map((o) => getOwnerDisplayName(ownerLookup, o, o))
                          .join(", ")}
                      </td>
                      <td className="p-2 text-right align-top">
                        <button
                          type="button"
                          onClick={() => toggleHoldingRemoval(row.key)}
                          className={`rounded px-2 py-1 text-xs transition-colors ${
                            row.isRemoved
                              ? "border border-green-300 text-green-600 hover:bg-green-50"
                              : "border border-red-300 text-red-600 hover:bg-red-50"
                          }`}
                        >
                          {row.isRemoved ? t("scenarioTester.restore") : t("scenarioTester.remove")}
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
              <tfoot>
                <tr className="bg-slate-50">
                  <td className="p-2 font-semibold" colSpan={3}>
                    {t("scenarioTester.total")}
                  </td>
                  <td className="p-2 text-right font-semibold">
                    {fmt.format(totalMarketValue)}
                  </td>
                  <td colSpan={3}></td>
                </tr>
              </tfoot>
            </table>
            {combinedHoldings.length > MAX_SCENARIO_HOLDING_ROWS && (
              <p className="mt-2 text-xs text-slate-500">
                {t("scenarioTester.showingFirst", {
                  shown: MAX_SCENARIO_HOLDING_ROWS.toLocaleString(),
                  total: combinedHoldings.length.toLocaleString(),
                })}
              </p>
            )}
          </div>
        )}
      </section>

      <section className="rounded-md border border-slate-200 bg-white p-4 text-slate-900 shadow-sm">
        <div className="mb-3 flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
          <h2 className="text-lg font-semibold">{t("scenarioTester.save.title")}</h2>
          <button
            type="button"
            onClick={downloadScenario}
            className="rounded bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow hover:bg-indigo-700"
            disabled={activeHoldings.length === 0}
          >
            {t("scenarioTester.save.download")}
          </button>
        </div>
        <p className="text-sm text-slate-600">
          {t("scenarioTester.save.description")}
        </p>
      </section>

      <section className="rounded-md border border-slate-200 bg-white p-4 text-slate-900 shadow-sm">
        <h2 className="mb-3 text-lg font-semibold">{t("scenarioTester.stress.title")}</h2>
        <p className="mb-4 text-sm text-slate-600">
          {t("scenarioTester.stress.description")}
        </p>
        <div className="mb-4 flex flex-col gap-2 md:flex-row md:items-center">
          <select
            value={eventId}
            onChange={(e) => setEventId(e.target.value)}
            className="rounded border border-slate-300 px-3 py-2 md:mr-2"
          >
            <option value="">{t("scenarioTester.stress.selectEvent")}</option>
            {events.map((ev) => (
              <option key={ev.id} value={ev.id}>
                {ev.name}
              </option>
            ))}
          </select>
          <div className="flex flex-wrap items-center gap-2 md:mr-2">
            {HORIZONS.map((h) => (
              <label key={h} className="flex items-center gap-1 text-sm">
                <input
                  type="checkbox"
                  checked={horizons.includes(h)}
                  onChange={() => toggleHorizon(h)}
                />
                {h}
              </label>
            ))}
          </div>
          <button
            onClick={handleRun}
            disabled={!canRun}
            className="rounded bg-slate-800 px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:bg-slate-400"
          >
            {t("scenarioTester.stress.run")}
          </button>
        </div>
        {error && <div className="mb-3 text-sm text-red-500">{error}</div>}
        {results && (
          <div className="overflow-auto">
            <table className="min-w-full border border-slate-200 text-sm">
              <thead className="bg-slate-50">
                <tr>
                  <th className="p-2 text-left">{t("scenarioTester.stress.owner")}</th>
                  {horizons.flatMap((h) => [
                    <th key={`${h}-b`} className="p-2 text-right">
                      {t("scenarioTester.stress.baseline", { horizon: h })}
                    </th>,
                    <th key={`${h}-s`} className="p-2 text-right">
                      {t("scenarioTester.stress.shocked", { horizon: h })}
                    </th>,
                    <th key={`${h}-p`} className="p-2 text-right">
                      {t("scenarioTester.stress.impact", { horizon: h })}
                    </th>,
                  ])}
                </tr>
              </thead>
              <tbody>
                {results.map((r, i) => (
                  <tr key={i} className="border-t">
                    <td className="p-2 font-medium">{r.owner}</td>
                    {horizons.map((h) => {
                      const data = r.horizons[h];
                      const baseline = data?.baseline_total_value_gbp ?? null;
                      const shocked = data?.shocked_total_value_gbp ?? null;
                      const pct =
                        baseline != null && shocked != null
                          ? ((shocked - baseline) / baseline) * 100.0
                          : null;
                      const coverage = data?.coverage_pct ?? null;
                      const partial = coverage != null && coverage < 100;
                      return (
                        <Fragment key={h}>
                          <td className="p-2 text-right">
                            {baseline != null ? fmt.format(baseline) : "—"}
                          </td>
                          <td className="p-2 text-right">
                            {shocked != null ? fmt.format(shocked) : "—"}
                          </td>
                          <td
                            className="p-2 text-right"
                            title={
                              partial
                                ? t("scenarioTester.stress.coverageTitle", {
                                    pct: coverage.toFixed(0),
                                  })
                                : undefined
                            }
                          >
                            {pct != null
                              ? `${pct.toFixed(2)}%`
                              : "—"}
                            {partial && (
                              <span className="block text-xs text-slate-500">
                                {t("scenarioTester.stress.priced", { pct: coverage.toFixed(0) })}
                              </span>
                            )}
                          </td>
                        </Fragment>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-2 text-xs text-slate-500">
              {t("scenarioTester.stress.footnote")}
            </p>
          </div>
        )}
      </section>

      <FxShockPanel />
    </div>
  );
}
