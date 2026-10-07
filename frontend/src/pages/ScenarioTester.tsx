import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { getOwners, getPortfolio } from "../api";
import type { OwnerSummary, Portfolio, SyntheticHolding } from "../types";
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
import StrategyStressPanel from "../components/StrategyStressPanel";

type PortfolioState = {
  status: "idle" | "loading" | "ready" | "error";
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

export default function ScenarioTester() {
  const { t } = useTranslation();
  const [owners, setOwners] = useState<OwnerSummary[]>([]);
  const [portfolioStates, setPortfolioStates] = useState<Record<string, PortfolioState>>({});
  const [ownerError, setOwnerError] = useState<string | null>(null);
  const [selectedOwners, setSelectedOwners] = useState<string[]>(() =>
    loadJSON<string[]>("scenario.selectedOwners", []),
  );
  const [stressOwner, setStressOwner] = useState("");
  const [customHoldings, setCustomHoldings] = useState<CustomHolding[]>(() =>
    loadJSON<CustomHolding[]>("scenario.customHoldings", []),
  );
  const [removedKeys, setRemovedKeys] = useState<Set<string>>(() => new Set());

  // Market values and scenario results are GBP amounts; money() labels them,
  // it does not convert, so they stay labelled GBP (#9725).
  const fmt = { format: (v: number) => money(v, "GBP") };

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
    saveJSON("scenario.customHoldings", customHoldings);
  }, [customHoldings]);

  const ownerLookup = useMemo(
    () => createOwnerDisplayLookup(owners),
    [owners],
  );

  // The stress test runs for one owner: the chosen one, else the first
  // selected portfolio, else the first owner.
  const effectiveStressOwner =
    stressOwner || selectedOwners[0] || owners[0]?.owner || "";

  const { run: runPortfolioRequest } = useDedupedRequest<Portfolio>();

  const ensurePortfolioLoaded = useCallback(
    (owner: string) => {
      // A loaded owner keeps its data: the deduped request below is skipped
      // for it, so marking it loading again would hide its holdings.
      setPortfolioStates((prev) =>
        prev[owner]?.status === "ready"
          ? prev
          : { ...prev, [owner]: { status: "loading" } },
      );

      runPortfolioRequest(owner, () => getPortfolio(owner))
        .then((pf) => {
          if (pf === undefined) {
            return;
          }
          setPortfolioStates((prev) =>
            prev[owner]
              ? { ...prev, [owner]: { status: "ready", data: pf } }
              : prev,
          );
        })
        .catch((e) => {
          const msg = e instanceof Error ? e.message : String(e);
          setPortfolioStates((prev) =>
            prev[owner]
              ? { ...prev, [owner]: { status: "error", error: msg } }
              : prev,
          );
        });
    },
    [runPortfolioRequest],
  );

  useEffect(() => {
    if (selectedOwners.length === 0) return;
    selectedOwners.forEach((owner) => ensurePortfolioLoaded(owner));
  }, [selectedOwners, ensurePortfolioLoaded]);

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

  function downloadScenario() {
    if (activeHoldings.length === 0) {
      return;
    }
    const payload = {
      generated_at: new Date().toISOString(),
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
      const datePart = new Date().toISOString().slice(0, 10);
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
      <section className="rounded-md border border-[var(--surface-card-border)] bg-[var(--surface-card-bg)] p-4 text-[var(--surface-card-color)] shadow-sm">
        <header className="mb-3 flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
          <h1 className="text-xl font-semibold">{t("scenarioTester.title")}</h1>
          <div className="flex flex-wrap gap-2">
            <button
              className="rounded border border-[var(--surface-card-border)] bg-transparent px-3 py-1 text-sm hover:bg-[var(--menu-hover-bg)] disabled:cursor-not-allowed disabled:opacity-50"
              type="button"
              onClick={handleSelectAllOwners}
              disabled={!ownersLoaded}
            >
              {t("scenarioTester.selectAll")}
            </button>
            <button
              className="rounded border border-[var(--surface-card-border)] bg-transparent px-3 py-1 text-sm hover:bg-[var(--menu-hover-bg)] disabled:cursor-not-allowed disabled:opacity-50"
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
                className="flex flex-col gap-1 rounded border border-[var(--surface-card-border)] p-3 hover:border-indigo-400"
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
                  <span className="text-xs text-[var(--surface-muted-color)]">{statusLabel}</span>
                ) : null}
                <span className="text-xs text-[var(--surface-muted-color)]">
                  {t("scenarioTester.accounts", { count: owner.accounts?.length ?? 0 })}
                </span>
              </label>
            );
          })}
          {owners.length === 0 && !ownerError && (
            <p className="text-sm text-[var(--surface-muted-color)]">{t("scenarioTester.loadingPortfolios")}</p>
          )}
        </div>
      </section>

      <section className="rounded-md border border-[var(--surface-card-border)] bg-[var(--surface-card-bg)] p-4 text-[var(--surface-card-color)] shadow-sm">
        <div className="mb-3 flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
          <h2 className="text-lg font-semibold">{t("scenarioTester.positions")}</h2>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={resetRemovals}
              className="rounded border border-[var(--surface-card-border)] bg-transparent px-3 py-1 text-sm hover:bg-[var(--menu-hover-bg)] disabled:cursor-not-allowed disabled:opacity-50"
              disabled={removedKeys.size === 0}
            >
              {t("scenarioTester.restoreRemoved")}
            </button>
            <button
              type="button"
              onClick={handleAddCustomHolding}
              className="rounded border border-indigo-500 bg-transparent px-3 py-1 text-sm text-indigo-500 hover:bg-[var(--menu-hover-bg)]"
            >
              {t("scenarioTester.addCustom")}
            </button>
            <button
              type="button"
              onClick={clearCustomHoldings}
              className="rounded border border-[var(--surface-card-border)] bg-transparent px-3 py-1 text-sm hover:bg-[var(--menu-hover-bg)] disabled:cursor-not-allowed disabled:opacity-50"
              disabled={customHoldings.length === 0}
            >
              {t("scenarioTester.removeCustom")}
            </button>
          </div>
        </div>

        {selectedOwners.length === 0 && customHoldings.length === 0 ? (
          <p className="text-sm text-[var(--surface-muted-color)]">
            {t("scenarioTester.emptyState")}
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full border border-[var(--surface-card-border)] text-sm">
              <thead className="bg-[var(--tab-active-bg)]">
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
                            className="rounded border border-red-400 bg-transparent px-2 py-1 text-xs text-red-500 hover:bg-[var(--menu-hover-bg)]"
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
                        row.isRemoved ? "bg-red-500/10 text-[var(--surface-muted-color)]" : ""
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
                      <td className="p-2 align-top text-xs text-[var(--surface-muted-color)]">
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
                              ? "border border-green-500 bg-transparent text-green-500 hover:bg-[var(--menu-hover-bg)]"
                              : "border border-red-400 bg-transparent text-red-500 hover:bg-[var(--menu-hover-bg)]"
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
                <tr className="bg-[var(--tab-active-bg)]">
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
              <p className="mt-2 text-xs text-[var(--surface-muted-color)]">
                {t("scenarioTester.showingFirst", {
                  shown: MAX_SCENARIO_HOLDING_ROWS.toLocaleString(),
                  total: combinedHoldings.length.toLocaleString(),
                })}
              </p>
            )}
          </div>
        )}
      </section>

      <section className="rounded-md border border-[var(--surface-card-border)] bg-[var(--surface-card-bg)] p-4 text-[var(--surface-card-color)] shadow-sm">
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
        <p className="text-sm text-[var(--surface-muted-color)]">
          {t("scenarioTester.save.description")}
        </p>
      </section>

      <section className="rounded-md border border-[var(--surface-card-border)] bg-[var(--surface-card-bg)] p-4 text-[var(--surface-card-color)] shadow-sm">
        {owners.length > 1 && (
          <label className="mb-3 flex items-center gap-2 text-sm">
            <span>{t("scenarioTester.stressOwner")}</span>
            <select
              value={effectiveStressOwner}
              onChange={(e) => setStressOwner(e.target.value)}
              className="rounded border border-slate-300 px-2 py-1"
            >
              {owners.map((o) => (
                <option key={o.owner} value={o.owner}>
                  {getOwnerDisplayName(ownerLookup, o.owner)}
                </option>
              ))}
            </select>
          </label>
        )}
        {effectiveStressOwner && (
          <StrategyStressPanel
            key={effectiveStressOwner}
            owner={effectiveStressOwner}
          />
        )}
      </section>

      <FxShockPanel />
    </div>
  );
}
