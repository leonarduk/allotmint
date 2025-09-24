import { useEffect, useRef, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { useParams, Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useInstrumentHistory, updateCachedInstrumentHistory } from "../hooks/useInstrumentHistory";
import { InstrumentDetail, InstrumentPositionsTable } from "../components/InstrumentDetail";
import {
  getNews,
  getScreener,
  listInstrumentMetadata,
  updateInstrumentMetadata,
} from "../api";
import type { NewsItem, InstrumentMetadata, ScreenerResult } from "../types";
import EmptyState from "../components/EmptyState";
import { useConfig, SUPPORTED_CURRENCIES } from "../ConfigContext";
import surfaceStyles from "../styles/surface.module.css";
import { formatDateISO } from "../lib/date";
import { money, percent } from "../lib/money";

function normaliseOptional(value: unknown) {
  if (typeof value !== "string") return undefined;
  const trimmed = value.trim();
  return trimmed || undefined;
}

function normaliseUppercase(value: unknown) {
  if (typeof value !== "string") return undefined;
  const trimmed = value.trim().toUpperCase();
  return trimmed || undefined;
}

type InstrumentResearchProps = {
  ticker?: string;
};

export default function InstrumentResearch({ ticker }: InstrumentResearchProps) {
  const { ticker: routeTicker } = useParams<{ ticker: string }>();
  const { t } = useTranslation();
  const resolvedTicker =
    typeof ticker === "string" && ticker ? ticker : routeTicker ?? "";
  const tkr =
    resolvedTicker && /^[A-Za-z0-9.-]{1,10}$/.test(resolvedTicker)
      ? resolvedTicker
      : "";
  const tickerParts = tkr.split(".", 2);
  const baseTicker = tickerParts[0] ?? "";
  const initialExchange = tickerParts.length > 1 ? tickerParts[1] ?? "" : "";
  const { tabs, disabledTabs, baseCurrency } = useConfig();
  const [overviewHistoryDays, setOverviewHistoryDays] = useState<number>(0);
  const {
    data: detail,
    loading: detailLoading,
    error: detailError,
  } = useInstrumentHistory(tkr, overviewHistoryDays);
  const [news, setNews] = useState<NewsItem[]>([]);
  const [newsLoading, setNewsLoading] = useState(false);
  const [newsError, setNewsError] = useState<string | null>(null);
  const [instrumentExchange, setInstrumentExchange] = useState(initialExchange);
  type MetadataState = { name: string; sector: string; currency: string };
  const [metadata, setMetadata] = useState<MetadataState>({
    name: "",
    sector: "",
    currency: "",
  });
  const [formValues, setFormValues] = useState<MetadataState>({
    name: "",
    sector: "",
    currency: "",
  });
  const [isEditingMetadata, setIsEditingMetadata] = useState(false);
  const isEditingMetadataRef = useRef(isEditingMetadata);
  const [metadataSaving, setMetadataSaving] = useState(false);
  const [metadataStatus, setMetadataStatus] = useState<
    { kind: "success" | "error"; text: string } | null
  >(null);
  const [sectorOptions, setSectorOptions] = useState<string[]>([]);
  const [inWatchlist, setInWatchlist] = useState(() => {
    const list = (localStorage.getItem("watchlistSymbols") || "")
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    return !!tkr && list.includes(tkr);
  });
  const [activeTab, setActiveTab] = useState<
    "overview" | "timeseries" | "positions" | "fundamentals" | "news"
  >("overview");
  const [fundamentals, setFundamentals] = useState<ScreenerResult | null>(null);
  const [fundamentalsLoading, setFundamentalsLoading] = useState(false);
  const [fundamentalsError, setFundamentalsError] = useState<string | null>(null);

  useEffect(() => {
    setInstrumentExchange(initialExchange);
    setIsEditingMetadata(false);
    setMetadataSaving(false);
    setMetadataStatus(null);
    setMetadata({ name: "", sector: "", currency: "" });
    setFormValues({ name: "", sector: "", currency: "" });
    setSectorOptions([]);
    setOverviewHistoryDays(0);
  }, [tkr, initialExchange]);

  useEffect(() => {
    isEditingMetadataRef.current = isEditingMetadata;
  }, [isEditingMetadata]);

  useEffect(() => {
    if (!detail) return;
    const name = normaliseOptional(detail.name);
    const sector = normaliseOptional(detail.sector);
    const currency = normaliseUppercase(detail.currency);
    setMetadata((prev) => ({
      name: name ?? prev.name,
      sector: sector ?? prev.sector,
      currency: currency ?? prev.currency,
    }));
    if (!isEditingMetadata) {
      setFormValues((prev) => ({
        name: name ?? prev.name,
        sector: sector ?? prev.sector,
        currency: currency ?? prev.currency,
      }));
    }
    if (!instrumentExchange) {
      const detailTicker = typeof detail.ticker === "string" ? detail.ticker : "";
      if (detailTicker) {
        const [, exch] = detailTicker.split(".", 2);
        if (exch) setInstrumentExchange(exch);
      }
    }
  }, [detail, isEditingMetadata, instrumentExchange]);

  useEffect(() => {
    if (!tkr) return;
    let cancelled = false;
    (async () => {
      try {
        const catalogue = await listInstrumentMetadata();
        if (cancelled) return;
        const sectors = new Set<string>();
        let matched: InstrumentMetadata | null = null;
        const target = tkr.toUpperCase();
        const base = baseTicker.toUpperCase();
        for (const entry of catalogue ?? []) {
          if (!entry) continue;
          if (typeof entry.sector === "string") {
            const trimmed = entry.sector.trim();
            if (trimmed) sectors.add(trimmed);
          }
          const tickerValue = typeof entry.ticker === "string" ? entry.ticker : "";
          if (!tickerValue) continue;
          const [sym] = tickerValue.split(".", 2);
          const upper = tickerValue.toUpperCase();
          if (!matched) {
            if (upper === target) {
              matched = entry;
            } else if (base && sym && sym.toUpperCase() === base) {
              matched = entry;
            }
          }
        }
        setSectorOptions(
          Array.from(sectors).sort((a, b) =>
            a.localeCompare(b, undefined, { sensitivity: "base" }),
          ),
        );
        if (matched) {
          const name = normaliseOptional(matched.name) ?? matched.name;
          const sector = normaliseOptional(matched.sector);
          const currency = normaliseUppercase(matched.currency);
          setMetadata((prev) => ({
            name: prev.name || name || "",
            sector: prev.sector || sector || "",
            currency: prev.currency || currency || "",
          }));
          if (!isEditingMetadataRef.current) {
            setFormValues((prev) => ({
              name: prev.name || name || "",
              sector: prev.sector || sector || "",
              currency: prev.currency || currency || "",
            }));
          }
          setInstrumentExchange((prev) => {
            if (prev) return prev;
            const exchange =
              normaliseUppercase((matched as InstrumentMetadata).exchange) ??
              (() => {
                const value = typeof matched?.ticker === "string" ? matched.ticker : "";
                const parts = value.split(".", 2);
                return parts.length > 1 ? parts[1]?.trim().toUpperCase() ?? "" : "";
              })();
            return exchange || prev;
          });
        }
      } catch (err) {
        if (cancelled) return;
        console.error(err);
        const baseMessage = t("instrumentDetail.metadataLoadError");
        const extra = err instanceof Error ? err.message : String(err);
        setMetadataStatus({ kind: "error", text: `${baseMessage} ${extra}` });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [tkr, baseTicker, t]);

  const updateFormField = (field: keyof MetadataState) => (value: string) => {
    setFormValues((prev) => ({ ...prev, [field]: value }));
    setMetadataStatus((prev) => (prev?.kind === "error" ? null : prev));
  };

  const handleStartEditing = () => {
    setFormValues(metadata);
    setMetadataStatus(null);
    setIsEditingMetadata(true);
  };

  const handleCancelEditing = () => {
    setFormValues(metadata);
    setIsEditingMetadata(false);
    setMetadataStatus((prev) => (prev?.kind === "success" ? prev : null));
  };

  const handleSaveMetadata = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!isEditingMetadata) return;
    const trimmedName = formValues.name.trim();
    const trimmedSector = formValues.sector.trim();
    const selectedCurrency = formValues.currency.trim().toUpperCase();
    if (!selectedCurrency || !SUPPORTED_CURRENCIES.includes(selectedCurrency)) {
      setMetadataStatus({ kind: "error", text: t("instrumentDetail.metadataCurrencyError") });
      return;
    }
    const exchange = instrumentExchange.trim().toUpperCase();
    if (!baseTicker || !exchange) {
      setMetadataStatus({ kind: "error", text: t("instrumentDetail.metadataMissingExchange") });
      return;
    }
    setMetadataSaving(true);
    setMetadataStatus(null);
    try {
      const payload: InstrumentMetadata = {
        ticker: `${baseTicker}.${exchange}`,
        exchange,
        name: trimmedName,
        sector: trimmedSector || null,
        currency: selectedCurrency,
      };
      await updateInstrumentMetadata(baseTicker, exchange, payload);
      setMetadata({
        name: trimmedName,
        sector: trimmedSector,
        currency: selectedCurrency,
      });
      setFormValues({
        name: trimmedName,
        sector: trimmedSector,
        currency: selectedCurrency,
      });
      setInstrumentExchange(exchange);
      setIsEditingMetadata(false);
      updateCachedInstrumentHistory(tkr, (cached) => {
        cached.name = trimmedName;
        cached.sector = trimmedSector;
        cached.currency = selectedCurrency;
      });
      if (trimmedSector) {
        setSectorOptions((prev) => {
          if (prev.some((entry) => entry.toUpperCase() === trimmedSector.toUpperCase())) {
            return prev;
          }
          return [...prev, trimmedSector].sort((a, b) =>
            a.localeCompare(b, undefined, { sensitivity: "base" }),
          );
        });
      }
      setMetadataStatus({ kind: "success", text: t("instrumentDetail.metadataSaveSuccess") });
    } catch (err) {
      console.error(err);
      const baseMessage = t("instrumentDetail.metadataSaveError");
      const extra = err instanceof Error ? err.message : String(err);
      setMetadataStatus({ kind: "error", text: `${baseMessage} ${extra}` });
    } finally {
      setMetadataSaving(false);
    }
  };

  useEffect(() => {
    if (!tkr) return;
    const newsCtrl = new AbortController();

    const fetchNews = async () => {
      setNewsLoading(true);
      setNewsError(null);
      try {
        const items = await getNews(tkr, newsCtrl.signal);
        setNews(items);
      } catch (err) {
        const error = err as { name?: string } | null | undefined;
        if (error?.name === "AbortError") {
          return;
        }
        console.error(err);
        setNews([]);
        setNewsError(err instanceof Error ? err.message : String(err));
      } finally {
        setNewsLoading(false);
      }
    };

    void fetchNews();
    return () => {
      newsCtrl.abort();
    };
  }, [tkr]);

  useEffect(() => {
    const list = (localStorage.getItem("watchlistSymbols") || "")
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    setInWatchlist(!!tkr && list.includes(tkr));
  }, [tkr]);

  useEffect(() => {
    if (!tkr || activeTab !== "fundamentals") return;
    const controller = new AbortController();
    let cancelled = false;

    const fetchFundamentals = async () => {
      setFundamentalsLoading(true);
      setFundamentalsError(null);
      setFundamentals(null);
      try {
        const results = await getScreener([tkr], {}, controller.signal);
        if (cancelled) return;
        const target = tkr.toUpperCase();
        const [baseTarget] = target.split(".", 1);
        const entry =
          results?.find((item) => {
            const tickerValue = (item?.ticker ?? "").toUpperCase();
            if (!tickerValue) return false;
            return (
              tickerValue === target || (!!baseTarget && tickerValue === baseTarget)
            );
          }) ?? results?.[0] ?? null;
        setFundamentals(entry ?? null);
      } catch (err) {
        const error = err as { name?: string } | null | undefined;
        if (error?.name === "AbortError") return;
        console.error(err);
        if (!cancelled) {
          const message = err instanceof Error ? err.message : String(err);
          setFundamentalsError(`Unable to load fundamentals: ${message}`);
        }
      } finally {
        if (!cancelled) {
          setFundamentalsLoading(false);
        }
      }
    };

    void fetchFundamentals();

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [tkr, activeTab]);

  function toggleWatchlist() {
    const list = (localStorage.getItem("watchlistSymbols") || "")
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    if (!tkr) return;
    if (list.includes(tkr)) {
      const updated = list.filter((s) => s !== tkr);
      localStorage.setItem("watchlistSymbols", updated.join(","));
      setInWatchlist(false);
    } else {
      list.push(tkr);
      localStorage.setItem("watchlistSymbols", list.join(","));
      setInWatchlist(true);
    }
  }

  const fallbackSector = detail ? normaliseOptional(detail.sector) : undefined;
  const fallbackCurrency = detail ? normaliseUppercase(detail.currency) : undefined;
  const displayName = metadata.name || detail?.name || null;
  const displaySector = metadata.sector || fallbackSector || "";
  const displayCurrency = metadata.currency || fallbackCurrency || "";
  const fundamentalsCurrency =
    (typeof detail?.base_currency === "string" && detail.base_currency) ||
    displayCurrency ||
    baseCurrency ||
    "USD";
  const instrumentType =
    detail && typeof (detail as { instrument_type?: unknown }).instrument_type === "string"
      ? ((detail as { instrument_type?: string }).instrument_type ?? null)
      : null;
  const positions = Array.isArray(detail?.positions) ? detail.positions : [];

  const tabOptions: { id: typeof activeTab; label: string }[] = [
    { id: "overview", label: "Overview" },
    { id: "timeseries", label: "Timeseries" },
    { id: "positions", label: "Positions" },
    { id: "fundamentals", label: "Fundamentals" },
    { id: "news", label: "News" },
  ];
  const standalonePalette = {
    positive: "#137333",
    negative: "#b3261e",
    link: "#1a73e8",
    muted: "#555",
  };

  if (!tkr) return <div>Invalid ticker</div>;

  return (
    <div style={{ maxWidth: 900, margin: "0 auto", padding: "1rem" }}>
      {(() => {
        const headingName = displayName;
        if (!headingName) {
          return <div style={{ marginBottom: "1rem" }}>{tkr}</div>;
        }
        return (
          <h1 style={{ marginBottom: "1rem" }}>
            {tkr} {` - ${headingName}`}
            {displaySector || displayCurrency ? (
              <span
                style={{
                  display: "block",
                  fontSize: "0.8rem",
                  fontWeight: "normal",
                }}
              >
                {displaySector}
                {displaySector && displayCurrency ? " · " : ""}
                {displayCurrency}
              </span>
            ) : null}
          </h1>
        );
      })()}

      <div style={{ marginBottom: "1rem" }}>
        {tabs.screener && !(disabledTabs ?? []).includes("screener") && (
          <Link to="/screener" style={{ marginRight: "1rem" }}>
            View Screener
          </Link>
        )}
        {tabs.watchlist && !(disabledTabs ?? []).includes("watchlist") && (
          <Link to="/watchlist">Watchlist</Link>
        )}
        <button onClick={toggleWatchlist} style={{ marginLeft: "1rem" }}>
          {inWatchlist ? "Remove from Watchlist" : "Add to Watchlist"}
        </button>
      </div>
      <form onSubmit={handleSaveMetadata} style={{ marginBottom: "1rem" }}>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            gap: "0.5rem",
            flexWrap: "wrap",
            marginBottom: "0.5rem",
          }}
        >
          <h2 style={{ margin: 0 }}>{t("instrumentDetail.infoHeading")}</h2>
          {isEditingMetadata ? (
            <div>
              <button
                type="submit"
                disabled={metadataSaving}
                style={{ marginRight: "0.5rem" }}
              >
                {t("instrumentDetail.save")}
              </button>
              <button
                type="button"
                onClick={handleCancelEditing}
                disabled={metadataSaving}
              >
                {t("instrumentDetail.cancel")}
              </button>
            </div>
          ) : (
            <button type="button" onClick={handleStartEditing}>
              {t("instrumentDetail.edit")}
            </button>
          )}
        </div>
        {metadataStatus && (
          <div
            style={{
              marginBottom: "0.5rem",
              color: metadataStatus.kind === "error" ? "red" : "green",
            }}
          >
            {metadataStatus.text}
          </div>
        )}
        <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
          <li style={{ marginBottom: "0.5rem" }}>
            {isEditingMetadata ? (
              <label htmlFor="instrument-name" style={{ display: "block" }}>
                {t("instrumentDetail.nameLabel")}
                <input
                  id="instrument-name"
                  value={formValues.name}
                  onChange={(e) => updateFormField("name")(e.target.value)}
                  style={{ display: "block", marginTop: "0.25rem", width: "100%" }}
                  disabled={metadataSaving}
                />
              </label>
            ) : (
              <span>
                {t("instrumentDetail.nameLabel")}: {displayName ?? "—"}
              </span>
            )}
          </li>
          <li style={{ marginBottom: "0.5rem" }}>
            {isEditingMetadata ? (
              <label htmlFor="instrument-sector" style={{ display: "block" }}>
                {t("instrumentDetail.sectorLabel")}
                <input
                  id="instrument-sector"
                  list="instrument-sector-options"
                  value={formValues.sector}
                  onChange={(e) => updateFormField("sector")(e.target.value)}
                  style={{ display: "block", marginTop: "0.25rem", width: "100%" }}
                  disabled={metadataSaving}
                />
              </label>
            ) : (
              <span>
                {t("instrumentDetail.sectorLabel")}: {displaySector || "—"}
              </span>
            )}
          </li>
          <li>
            {isEditingMetadata ? (
              <label htmlFor="instrument-currency" style={{ display: "block" }}>
                {t("instrumentDetail.currencyLabel")}
                <select
                  id="instrument-currency"
                  value={formValues.currency}
                  onChange={(e) => updateFormField("currency")(e.target.value)}
                  style={{ display: "block", marginTop: "0.25rem" }}
                  disabled={metadataSaving}
                >
                  <option value="">{t("instrumentDetail.currencyPlaceholder")}</option>
                  {SUPPORTED_CURRENCIES.map((currency) => (
                    <option key={currency} value={currency}>
                      {currency}
                    </option>
                  ))}
                </select>
              </label>
            ) : (
              <span>
                {t("instrumentDetail.currencyLabel")}: {displayCurrency || "—"}
              </span>
            )}
          </li>
        </ul>
        {isEditingMetadata && (
          <datalist id="instrument-sector-options">
            {sectorOptions.map((sector) => (
              <option key={sector} value={sector} />
            ))}
          </datalist>
        )}
      </form>
      <div
        style={{
          display: "flex",
          gap: "0.5rem",
          borderBottom: "1px solid #ccc",
          marginTop: "1rem",
          marginBottom: "1rem",
        }}
      >
        {tabOptions.map((tab) => {
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveTab(tab.id)}
              aria-pressed={isActive}
              style={{
                border: "none",
                background: "transparent",
                padding: "0.5rem 0.75rem",
                borderBottom: isActive
                  ? "3px solid #333"
                  : "3px solid transparent",
                cursor: "pointer",
                fontWeight: isActive ? "bold" : "normal",
              }}
            >
              {tab.label}
            </button>
          );
        })}
      </div>

      {(() => {
        if (activeTab !== "overview") return null;

        const rawPrices = Array.isArray(detail?.prices)
          ? (detail?.prices as unknown[])
          : [];
        const parsedPrices = rawPrices
          .map((entry) => {
            if (!entry || typeof entry !== "object") return null;
            const value = entry as Record<string, unknown>;
            const closeCandidates = [
              value.close_gbp,
              value.close,
              value.close_usd,
            ];
            const close = closeCandidates.find(
              (v) => typeof v === "number" && Number.isFinite(v),
            ) as number | undefined;
            if (close == null) return null;
            const date = typeof value.date === "string" ? value.date : null;
            return { close, date };
          })
          .filter((v): v is { close: number; date: string | null } => v != null);

        const computeWindowChange = (window: number) => {
          if (parsedPrices.length < 2) return null;
          const subset = parsedPrices.slice(-Math.max(window, 2));
          if (subset.length < 2) return null;
          const first = subset[0].close;
          const last = subset[subset.length - 1]?.close;
          if (!Number.isFinite(first) || !Number.isFinite(last) || first === 0) {
            return null;
          }
          return (last - first) / first;
        };

        const priceValues = parsedPrices.map((entry) => entry.close);
        const dailyReturns = priceValues.reduce<number[]>((acc, value, index) => {
          if (index === 0) return acc;
          const prev = priceValues[index - 1];
          if (!Number.isFinite(prev) || prev === 0 || !Number.isFinite(value)) {
            return acc;
          }
          acc.push(value / prev - 1);
          return acc;
        }, []);

        const recentReturns = dailyReturns.slice(-30);
        const meanReturn =
          recentReturns.length > 0
            ? recentReturns.reduce((sum, r) => sum + r, 0) / recentReturns.length
            : null;
        const volatility = (() => {
          if (recentReturns.length < 2) return null;
          const avg =
            recentReturns.reduce((sum, r) => sum + r, 0) / recentReturns.length;
          const variance =
            recentReturns.reduce((sum, r) => sum + (r - avg) ** 2, 0) /
            (recentReturns.length - 1);
          if (!Number.isFinite(variance)) return null;
          const dailyVol = Math.sqrt(variance);
          return dailyVol * Math.sqrt(252);
        })();
        const worstDailyReturn =
          recentReturns.length > 0
            ? recentReturns.reduce(
                (min, value) => (value < min ? value : min),
                recentReturns[0] ?? 0,
              )
            : null;
        const maxDrawdown = (() => {
          if (!priceValues.length) return null;
          let peak = priceValues[0];
          let maxDrop = 0;
          for (const price of priceValues) {
            if (!Number.isFinite(price)) continue;
            if (price > peak) {
              peak = price;
              continue;
            }
            if (peak <= 0) continue;
            const drop = (peak - price) / peak;
            if (drop > maxDrop) {
              maxDrop = drop;
            }
          }
          return maxDrop || null;
        })();

        const change7d = computeWindowChange(7);
        const change30d = computeWindowChange(30);
        const latestPriceEntry =
          parsedPrices.length > 0 ? parsedPrices[parsedPrices.length - 1] : null;
        const latestPrice = latestPriceEntry?.close ?? null;
        const latestDate = (() => {
          if (!latestPriceEntry?.date) return null;
          const parsed = new Date(latestPriceEntry.date);
          if (Number.isNaN(parsed.getTime())) return latestPriceEntry.date;
          return formatDateISO(parsed);
        })();
        const formattedCoverage = (() => {
          const from =
            typeof detail?.from === "string" && detail.from
              ? detail.from
              : null;
          const to =
            typeof detail?.to === "string" && detail.to ? detail.to : null;
          if (from && to) return `${from} → ${to}`;
          if (from) return `${from} → —`;
          if (to) return `— → ${to}`;
          return "—";
        })();
        const rowsCount =
          typeof detail?.rows === "number" && Number.isFinite(detail.rows)
            ? detail.rows.toLocaleString()
            : "—";

        const priceCurrency =
          (typeof detail?.base_currency === "string" && detail.base_currency) ||
          displayCurrency ||
          baseCurrency;

        const percentValue = (ratio: number | null, digits = 2) => {
          if (ratio == null || !Number.isFinite(ratio)) return "—";
          return percent(ratio * 100, digits);
        };

        const summarySections: {
          title: string;
          items: { label: string; value: ReactNode }[];
        }[] = [
          {
            title: "Key Facts",
            items: [
              { label: "Ticker", value: tkr },
              { label: "Exchange", value: instrumentExchange || "—" },
              { label: "Sector", value: displaySector || "—" },
              { label: "Currency", value: displayCurrency || "—" },
              {
                label: "Last Close",
                value: latestPrice != null
                  ? money(latestPrice, priceCurrency)
                  : "—",
              },
              { label: "As of", value: latestDate ?? "—" },
              { label: "Coverage", value: formattedCoverage },
              { label: "Data Points", value: rowsCount },
            ],
          },
          {
            title: "Performance",
            items: [
              { label: "7d Change", value: percentValue(change7d, 2) },
              { label: "30d Change", value: percentValue(change30d, 2) },
              {
                label: "Average Daily Return (30d)",
                value: percentValue(meanReturn, 2),
              },
            ],
          },
          {
            title: "Risk",
            items: [
              {
                label: "Annualised Volatility (30d)",
                value: percentValue(volatility, 2),
              },
              {
                label: "Max Drawdown",
                value: percentValue(maxDrawdown != null ? -maxDrawdown : null, 2),
              },
              {
                label: "Worst Day (30d)",
                value: percentValue(worstDailyReturn, 2),
              },
            ],
          },
        ];

        return (
          <div style={{ marginBottom: "2rem" }}>
            <h2 style={{ marginBottom: "0.75rem" }}>Summary</h2>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
                gap: "1rem",
              }}
            >
              {summarySections.map((section) => (
                <div key={section.title} className={surfaceStyles.surfaceCard}>
                  <h3 className={surfaceStyles.surfaceCardTitle}>{section.title}</h3>
                  <dl style={{ margin: 0 }}>
                    {section.items.map((item) => (
                      <div
                        key={item.label}
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          gap: "0.75rem",
                          fontSize: "0.9rem",
                          marginBottom: "0.5rem",
                          alignItems: "baseline",
                        }}
                      >
                        <dt
                          className={surfaceStyles.surfaceMuted}
                          style={{ margin: 0 }}
                        >
                          {item.label}
                        </dt>
                        <dd
                          style={{
                            margin: 0,
                            fontWeight: 500,
                            textAlign: "right",
                            flex: "0 0 auto",
                          }}
                        >
                          {item.value}
                        </dd>
                      </div>
                    ))}
                  </dl>
                </div>
              ))}
            </div>
          </div>
        );
      })()}

      {activeTab === "timeseries" && (
        <div style={{ marginBottom: "2rem" }}>
          <InstrumentDetail
            ticker={tkr}
            name={displayName ?? tkr}
            currency={displayCurrency || undefined}
            instrument_type={instrumentType}
            variant="standalone"
            hidePositions
            initialHistoryDays={overviewHistoryDays}
            onHistoryRangeChange={setOverviewHistoryDays}
          />
        </div>
      )}

      {activeTab === "positions" && (
        detailError ? (
          <div>{detailError.message}</div>
        ) : (
          <InstrumentPositionsTable
            positions={positions}
            loading={detailLoading}
            positiveColor={standalonePalette.positive}
            negativeColor={standalonePalette.negative}
            linkColor={standalonePalette.link}
            mutedColor={standalonePalette.muted}
          />
        )
      )}

      {activeTab === "fundamentals" && (
        <div style={{ marginBottom: "2rem" }}>
          <h2 style={{ marginBottom: "0.75rem" }}>Fundamentals</h2>
          {fundamentalsLoading ? (
            <div>Loading fundamentals...</div>
          ) : fundamentalsError ? (
            <div style={{ color: "red" }}>{fundamentalsError}</div>
          ) : !fundamentals ? (
            <p style={{ margin: 0, color: "#555" }}>
              Fundamentals data is not available for this instrument.
            </p>
          ) : (
            (() => {
              const formatRatio = (
                value: number | null | undefined,
                options?: Intl.NumberFormatOptions,
              ) => {
                if (value == null || !Number.isFinite(value)) return "—";
                const formatter = new Intl.NumberFormat(undefined, {
                  minimumFractionDigits: 2,
                  maximumFractionDigits: 2,
                  ...options,
                });
                return formatter.format(value);
              };
              const formatPercent = (
                value: number | null | undefined,
                digits = 2,
              ) => {
                if (value == null || !Number.isFinite(value)) return "—";
                return percent(value * 100, digits);
              };
              const formatInteger = (value: number | null | undefined) => {
                if (value == null || !Number.isFinite(value)) return "—";
                return Math.round(value).toLocaleString();
              };

              const sections: {
                title: string;
                rows: { label: string; value: string }[];
              }[] = [
                {
                  title: "Valuation",
                  rows: [
                    { label: "PEG Ratio", value: formatRatio(fundamentals.peg_ratio) },
                    { label: "P/E Ratio", value: formatRatio(fundamentals.pe_ratio) },
                    {
                      label: "Market Cap",
                      value: money(fundamentals.market_cap, fundamentalsCurrency),
                    },
                    {
                      label: "Free Cash Flow",
                      value: money(fundamentals.fcf, fundamentalsCurrency),
                    },
                    {
                      label: "Earnings Per Share",
                      value: formatRatio(fundamentals.eps),
                    },
                  ],
                },
                {
                  title: "Financial Health",
                  rows: [
                    { label: "Debt/Equity", value: formatRatio(fundamentals.de_ratio) },
                    {
                      label: "Long-Term Debt/Equity",
                      value: formatRatio(fundamentals.lt_de_ratio),
                    },
                    {
                      label: "Interest Coverage",
                      value: formatRatio(fundamentals.interest_coverage),
                    },
                    {
                      label: "Current Ratio",
                      value: formatRatio(fundamentals.current_ratio),
                    },
                    {
                      label: "Quick Ratio",
                      value: formatRatio(fundamentals.quick_ratio),
                    },
                  ],
                },
                {
                  title: "Profitability",
                  rows: [
                    {
                      label: "Gross Margin",
                      value: formatPercent(fundamentals.gross_margin),
                    },
                    {
                      label: "Operating Margin",
                      value: formatPercent(fundamentals.operating_margin),
                    },
                    {
                      label: "Net Margin",
                      value: formatPercent(fundamentals.net_margin),
                    },
                    {
                      label: "EBITDA Margin",
                      value: formatPercent(fundamentals.ebitda_margin),
                    },
                    { label: "ROA", value: formatPercent(fundamentals.roa) },
                    { label: "ROE", value: formatPercent(fundamentals.roe) },
                    { label: "ROI", value: formatPercent(fundamentals.roi) },
                  ],
                },
                {
                  title: "Shareholder Metrics",
                  rows: [
                    {
                      label: "Dividend Yield",
                      value: formatPercent(fundamentals.dividend_yield),
                    },
                    {
                      label: "Dividend Payout Ratio",
                      value: formatPercent(fundamentals.dividend_payout_ratio),
                    },
                    { label: "Beta", value: formatRatio(fundamentals.beta) },
                    {
                      label: "Shares Outstanding",
                      value: formatInteger(fundamentals.shares_outstanding),
                    },
                    {
                      label: "Float Shares",
                      value: formatInteger(fundamentals.float_shares),
                    },
                    {
                      label: "52 Week High",
                      value: money(fundamentals.high_52w, fundamentalsCurrency),
                    },
                    {
                      label: "52 Week Low",
                      value: money(fundamentals.low_52w, fundamentalsCurrency),
                    },
                    {
                      label: "Average Volume",
                      value: formatInteger(fundamentals.avg_volume),
                    },
                  ],
                },
              ];

              return (
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
                    gap: "1rem",
                  }}
                >
                  {sections.map((section) => (
                    <div key={section.title} className={surfaceStyles.surfaceCard}>
                      <h3 className={surfaceStyles.surfaceCardTitle}>{section.title}</h3>
                      <table
                        aria-label={`${section.title} fundamentals`}
                        style={{ width: "100%", borderCollapse: "collapse" }}
                      >
                        <tbody>
                          {section.rows.map((row) => (
                            <tr key={row.label}>
                              <th
                                scope="row"
                                style={{
                                  textAlign: "left",
                                  padding: "0.35rem 0",
                                  fontWeight: 500,
                                }}
                                className={surfaceStyles.surfaceMuted}
                              >
                                {row.label}
                              </th>
                              <td
                                style={{
                                  textAlign: "right",
                                  padding: "0.35rem 0",
                                  fontWeight: 600,
                                }}
                              >
                                {row.value}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ))}
                </div>
              );
            })()
          )}
        </div>
      )}

      {activeTab === "news" && (
        <>
          {newsLoading ? (
            <div>Loading news...</div>
          ) : newsError ? (
            <div>{newsError}</div>
          ) : news.length === 0 ? (
            <EmptyState message="No news available" />
          ) : (
            <div>
              <h2>News</h2>
              <ul>
                {news.map((n, i) => {
                  const publishedDate = n.published_at
                    ? new Date(n.published_at)
                    : null;
                  const formattedDate =
                    publishedDate && !Number.isNaN(publishedDate.getTime())
                      ? formatDateISO(publishedDate)
                      : null;
                  return (
                    <li key={i}>
                      <a href={n.url} target="_blank" rel="noopener noreferrer">
                        {n.headline}
                      </a>
                      {(n.source || formattedDate) && (
                        <div
                          style={{
                            fontSize: "0.875rem",
                            color: "#666",
                            marginTop: "0.25rem",
                          }}
                        >
                          {n.source && <span>{n.source}</span>}
                          {n.source && formattedDate ? " · " : null}
                          {formattedDate && <span>{formattedDate}</span>}
                        </div>
                      )}
                    </li>
                  );
                })}
              </ul>
            </div>
          )}
        </>
      )}
    </div>
  );
}
