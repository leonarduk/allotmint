import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { useParams, Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useInstrumentHistory, getCachedInstrumentHistory } from "../hooks/useInstrumentHistory";
import { InstrumentHistoryChart } from "../components/InstrumentHistoryChart";
import {
  getScreener,
  getNews,
  getQuotes,
  listInstrumentMetadata,
  updateInstrumentMetadata,
} from "../api";
import type {
  ScreenerResult,
  NewsItem,
  QuoteRow,
  InstrumentMetadata,
} from "../types";
import EmptyState from "../components/EmptyState";
import { largeNumber, money, percent } from "../lib/money";
import { useConfig, SUPPORTED_CURRENCIES } from "../ConfigContext";
import { formatDateISO } from "../lib/date";
import tableStyles from "../styles/table.module.css";
import { ArrowDownRight, ArrowUpRight } from "lucide-react";

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

export default function InstrumentResearch() {
  const { ticker } = useParams<{ ticker: string }>();
  const [metrics, setMetrics] = useState<ScreenerResult | null>(null);
  const [days, setDays] = useState(30);
  const [showBollinger, setShowBollinger] = useState(false);
  const { t } = useTranslation();
  const tkr = ticker && /^[A-Za-z0-9.-]{1,10}$/.test(ticker) ? ticker : "";
  const tickerParts = tkr.split(".", 2);
  const baseTicker = tickerParts[0] ?? "";
  const initialExchange = tickerParts.length > 1 ? tickerParts[1] ?? "" : "";
  const { tabs, disabledTabs, baseCurrency } = useConfig();
  const {
    data: detail,
    loading: detailLoading,
    error: detailError,
  } = useInstrumentHistory(tkr, days);
  const historyPrices = detail?.mini?.[String(days)] ?? [];
  const [quote, setQuote] = useState<QuoteRow | null>(null);
  const [news, setNews] = useState<NewsItem[]>([]);
  const [screenerLoading, setScreenerLoading] = useState(false);
  const [screenerError, setScreenerError] = useState<string | null>(null);
  const [quoteLoading, setQuoteLoading] = useState(false);
  const [quoteError, setQuoteError] = useState<string | null>(null);
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
  const [activeTab, setActiveTab] = useState<"fundamentals" | "timeseries" | "news">(
    "fundamentals",
  );

  useEffect(() => {
    setInstrumentExchange(initialExchange);
    setIsEditingMetadata(false);
    setMetadataSaving(false);
    setMetadataStatus(null);
    setMetadata({ name: "", sector: "", currency: "" });
    setFormValues({ name: "", sector: "", currency: "" });
    setSectorOptions([]);
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
      const cached = getCachedInstrumentHistory(tkr);
      if (cached) {
        cached.name = trimmedName;
        cached.sector = trimmedSector;
        cached.currency = selectedCurrency;
      }
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
    const screenerCtrl = new AbortController();
    const newsCtrl = new AbortController();
    const quoteCtrl = new AbortController();

    const fetchScreener = async () => {
      setScreenerLoading(true);
      setScreenerError(null);
      try {
        const rows = await getScreener([tkr], {}, screenerCtrl.signal);
        setMetrics(rows[0] || null);
      } catch (err) {
        const error = err as { name?: string } | null | undefined;
        if (error?.name === "AbortError") {
          return;
        }
        console.error(err);
        setMetrics(null);
        setScreenerError(err instanceof Error ? err.message : String(err));
      } finally {
        setScreenerLoading(false);
      }
    };

    const fetchQuote = async () => {
      setQuoteLoading(true);
      setQuoteError(null);
      try {
        const rows = await getQuotes([tkr], quoteCtrl.signal);
        setQuote(rows[0] || null);
      } catch (err) {
        const error = err as { name?: string } | null | undefined;
        if (error?.name === "AbortError") {
          return;
        }
        console.error(err);
        setQuote(null);
        setQuoteError(err instanceof Error ? err.message : String(err));
      } finally {
        setQuoteLoading(false);
      }
    };

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

    void fetchScreener();
    void fetchQuote();
    void fetchNews();
    return () => {
      screenerCtrl.abort();
      newsCtrl.abort();
      quoteCtrl.abort();
    };
  }, [tkr]);

  useEffect(() => {
    const list = (localStorage.getItem("watchlistSymbols") || "")
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    setInWatchlist(!!tkr && list.includes(tkr));
  }, [tkr]);

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
  const displayName =
    metadata.name || quote?.name || metrics?.name || detail?.name || null;
  const displaySector = metadata.sector || fallbackSector || "";
  const displayCurrency = metadata.currency || fallbackCurrency || "";

  type DetailPrice = {
    date?: string | null;
    close_gbp?: number | null;
    close?: number | null;
  };

  const toFiniteNumber = (value: unknown) =>
    typeof value === "number" && Number.isFinite(value) ? value : NaN;

  const priceHistory = Array.isArray(detail?.prices)
    ? (detail?.prices as DetailPrice[])
        .map((entry) => {
          const date = typeof entry?.date === "string" ? entry.date : "";
          const closeValue = toFiniteNumber(
            (entry?.close_gbp ?? entry?.close) ?? undefined,
          );
          return { date, close_gbp: closeValue };
        })
        .filter((entry) => entry.date && Number.isFinite(entry.close_gbp))
    : [];

  const priceHistoryWithChanges = priceHistory.map((entry, index, arr) => {
    const prev = arr[index - 1];
    const change_gbp = prev ? entry.close_gbp - prev.close_gbp : NaN;
    const change_pct = prev ? (change_gbp / prev.close_gbp) * 100 : NaN;
    return { ...entry, change_gbp, change_pct };
  });

  const tabOptions: { id: typeof activeTab; label: string }[] = [
    { id: "fundamentals", label: "Fundamentals" },
    { id: "timeseries", label: "Timeseries" },
    { id: "news", label: "News" },
  ];

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
      <div style={{ marginBottom: "0.5rem" }}>
        {[7, 30, 180, 365].map((d) => (
          <button
            key={d}
            onClick={() => setDays(d)}
            disabled={days === d}
            style={{ marginRight: "0.5rem" }}
          >
            {d}d
          </button>
        ))}
        <label style={{ marginLeft: "1rem", fontSize: "0.85rem" }}>
          <input
            type="checkbox"
            checked={showBollinger}
            onChange={(e) => setShowBollinger(e.target.checked)}
          />{" "}
          {t("instrumentDetail.bollingerBands")}
        </label>
      </div>
      {detailError && !detailLoading ? (
        <div
          style={{
            height: 220,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          History unavailable
        </div>
      ) : (
        <InstrumentHistoryChart
          data={historyPrices}
          loading={detailLoading}
          showBollinger={showBollinger}
        />
      )}
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

      {activeTab === "fundamentals" && (
        <>
          {(quoteLoading && screenerLoading) ? (
            <div>Loading quote...</div>
          ) : quoteError || screenerError ? (
            <div>{quoteError || screenerError}</div>
          ) : (
            (quote || metrics) && (
              <table style={{ marginBottom: "1rem" }}>
                <tbody>
                  <tr>
                    <th style={{ textAlign: "left", paddingRight: "0.5rem" }}>
                      Price
                    </th>
                    <td>{quote?.last ?? "—"}</td>
                  </tr>
                  <tr>
                    <th style={{ textAlign: "left", paddingRight: "0.5rem" }}>
                      Change %
                    </th>
                    <td>
                      {quote?.changePct != null
                        ? `${quote.changePct.toFixed(2)}%`
                        : "—"}
                    </td>
                  </tr>
                  <tr>
                    <th style={{ textAlign: "left", paddingRight: "0.5rem" }}>
                      Day Range
                    </th>
                    <td>
                      {quote
                        ? `${quote.low ?? "—"} - ${quote.high ?? "—"}`
                        : "—"}
                    </td>
                  </tr>
                  <tr>
                    <th style={{ textAlign: "left", paddingRight: "0.5rem" }}>
                      52W Range
                    </th>
                    <td>
                      {metrics
                        ? `${metrics.low_52w ?? "—"} - ${metrics.high_52w ?? "—"}`
                        : "—"}
                    </td>
                  </tr>
                </tbody>
              </table>
            )
          )}
          {screenerLoading ? (
            <div>Loading metrics...</div>
          ) : screenerError ? (
            <div>{screenerError}</div>
          ) : (
            metrics && (
              <table style={{ marginBottom: "1rem" }}>
                <tbody>
                  <tr>
                    <th style={{ textAlign: "left", paddingRight: "0.5rem" }}>
                      PEG
                    </th>
                    <td>{metrics.peg_ratio ?? "—"}</td>
                  </tr>
                  <tr>
                    <th style={{ textAlign: "left", paddingRight: "0.5rem" }}>
                      P/E
                    </th>
                    <td>{metrics.pe_ratio ?? "—"}</td>
                  </tr>
                  <tr>
                    <th style={{ textAlign: "left", paddingRight: "0.5rem" }}>
                      D/E
                    </th>
                    <td>{metrics.de_ratio ?? "—"}</td>
                  </tr>
                  <tr>
                    <th style={{ textAlign: "left", paddingRight: "0.5rem" }}>
                      LT D/E
                    </th>
                    <td>{metrics.lt_de_ratio ?? "—"}</td>
                  </tr>
                  <tr>
                    <th style={{ textAlign: "left", paddingRight: "0.5rem" }}>
                      Market Cap
                    </th>
                    <td>{largeNumber(metrics.market_cap)}</td>
                  </tr>
                  <tr>
                    <th style={{ textAlign: "left", paddingRight: "0.5rem" }}>
                      EPS
                    </th>
                    <td>{metrics.eps ?? "—"}</td>
                  </tr>
                  <tr>
                    <th style={{ textAlign: "left", paddingRight: "0.5rem" }}>
                      Dividend Yield
                    </th>
                    <td>{metrics.dividend_yield ?? "—"}</td>
                  </tr>
                  <tr>
                    <th style={{ textAlign: "left", paddingRight: "0.5rem" }}>
                      Beta
                    </th>
                    <td>{metrics.beta ?? "—"}</td>
                  </tr>
                  <tr>
                    <th style={{ textAlign: "left", paddingRight: "0.5rem" }}>
                      Avg Volume
                    </th>
                    <td>{largeNumber(metrics.avg_volume)}</td>
                  </tr>
                  <tr>
                    <th style={{ textAlign: "left", paddingRight: "0.5rem" }}>
                      Interest Coverage
                    </th>
                    <td>{metrics.interest_coverage ?? "—"}</td>
                  </tr>
                  <tr>
                    <th style={{ textAlign: "left", paddingRight: "0.5rem" }}>
                      Current Ratio
                    </th>
                    <td>{metrics.current_ratio ?? "—"}</td>
                  </tr>
                  <tr>
                    <th style={{ textAlign: "left", paddingRight: "0.5rem" }}>
                      Quick Ratio
                    </th>
                    <td>{metrics.quick_ratio ?? "—"}</td>
                  </tr>
                  <tr>
                    <th style={{ textAlign: "left", paddingRight: "0.5rem" }}>
                      FCF
                    </th>
                    <td>{largeNumber(metrics.fcf)}</td>
                  </tr>
                  <tr>
                    <th style={{ textAlign: "left", paddingRight: "0.5rem" }}>
                      Gross Margin
                    </th>
                    <td>{metrics.gross_margin ?? "—"}</td>
                  </tr>
                  <tr>
                    <th style={{ textAlign: "left", paddingRight: "0.5rem" }}>
                      Operating Margin
                    </th>
                    <td>{metrics.operating_margin ?? "—"}</td>
                  </tr>
                  <tr>
                    <th style={{ textAlign: "left", paddingRight: "0.5rem" }}>
                      Net Margin
                    </th>
                    <td>{metrics.net_margin ?? "—"}</td>
                  </tr>
                  <tr>
                    <th style={{ textAlign: "left", paddingRight: "0.5rem" }}>
                      EBITDA Margin
                    </th>
                    <td>{metrics.ebitda_margin ?? "—"}</td>
                  </tr>
                  <tr>
                    <th style={{ textAlign: "left", paddingRight: "0.5rem" }}>
                      ROA
                    </th>
                    <td>{metrics.roa ?? "—"}</td>
                  </tr>
                  <tr>
                    <th style={{ textAlign: "left", paddingRight: "0.5rem" }}>
                      ROE
                    </th>
                    <td>{metrics.roe ?? "—"}</td>
                  </tr>
                  <tr>
                    <th style={{ textAlign: "left", paddingRight: "0.5rem" }}>
                      ROI
                    </th>
                    <td>{metrics.roi ?? "—"}</td>
                  </tr>
                  <tr>
                    <th style={{ textAlign: "left", paddingRight: "0.5rem" }}>
                      Dividend Payout Ratio
                    </th>
                    <td>{metrics.dividend_payout_ratio ?? "—"}</td>
                  </tr>
                  <tr>
                    <th style={{ textAlign: "left", paddingRight: "0.5rem" }}>
                      Shares Outstanding
                    </th>
                    <td>{largeNumber(metrics.shares_outstanding)}</td>
                  </tr>
                  <tr>
                    <th style={{ textAlign: "left", paddingRight: "0.5rem" }}>
                      Float Shares
                    </th>
                    <td>{largeNumber(metrics.float_shares)}</td>
                  </tr>
                </tbody>
              </table>
            )
          )}
        </>
      )}

      {activeTab === "timeseries" && (
        <>
          {detailError ? (
            <div>{detailError.message}</div>
          ) : (
            <>
              <h2>{t("instrumentDetail.recentPrices")}</h2>
              <table
                className={tableStyles.table}
                style={{ fontSize: "0.85rem", marginBottom: "1rem" }}
              >
                <thead>
                  <tr>
                    <th className={tableStyles.cell}>
                      {t("instrumentDetail.priceColumns.date")}
                    </th>
                    <th className={`${tableStyles.cell} ${tableStyles.right}`}>
                      {t("instrumentDetail.priceColumns.close")}
                    </th>
                    <th className={`${tableStyles.cell} ${tableStyles.right}`}>
                      {t("instrumentDetail.priceColumns.delta")}
                    </th>
                    <th className={`${tableStyles.cell} ${tableStyles.right}`}>
                      {t("instrumentDetail.priceColumns.deltaPct")}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {detailLoading ? (
                    <tr>
                      <td
                        colSpan={4}
                        className={`${tableStyles.cell} ${tableStyles.center}`}
                        style={{ color: "#888" }}
                      >
                        {t("app.loading")}
                      </td>
                    </tr>
                  ) : priceHistoryWithChanges.length ? (
                    priceHistoryWithChanges
                      .slice(-60)
                      .reverse()
                      .map((p) => {
                        const colour = Number.isFinite(p.change_gbp)
                          ? p.change_gbp >= 0
                            ? "lightgreen"
                            : "red"
                          : undefined;
                        return (
                          <tr key={p.date}>
                            <td className={tableStyles.cell}>
                              {formatDateISO(new Date(p.date))}
                            </td>
                            <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                              {money(p.close_gbp, baseCurrency)}
                            </td>
                            <td
                              className={`${tableStyles.cell} ${tableStyles.right}`}
                              style={{ color: colour }}
                            >
                              {money(p.change_gbp, baseCurrency)}
                            </td>
                            <td
                              className={`${tableStyles.cell} ${tableStyles.right}`}
                              style={{ color: colour }}
                            >
                              {Number.isFinite(p.change_pct) ? (
                                <span
                                  style={{
                                    display: "inline-flex",
                                    alignItems: "center",
                                    justifyContent: "flex-end",
                                    gap: "0.25rem",
                                    fontVariantNumeric: "tabular-nums",
                                  }}
                                >
                                  {p.change_pct >= 0 ? (
                                    <ArrowUpRight size={12} />
                                  ) : (
                                    <ArrowDownRight size={12} />
                                  )}
                                  {percent(p.change_pct, 2)}
                                </span>
                              ) : (
                                percent(p.change_pct, 2)
                              )}
                            </td>
                          </tr>
                        );
                      })
                  ) : (
                    <tr>
                      <td
                        colSpan={4}
                        className={`${tableStyles.cell} ${tableStyles.center}`}
                        style={{ color: "#888" }}
                      >
                        {t("instrumentDetail.noPriceData")}
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </>
          )}
        </>
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
                {news.map((n, i) => (
                  <li key={i}>
                    <a href={n.url} target="_blank" rel="noopener noreferrer">
                      {n.headline}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}

      {detailLoading ? (
        <div>Loading instrument details...</div>
      ) : detailError ? (
        <div>{detailError.message}</div>
      ) : (
        detail && detail.positions && detail.positions.length > 0 && (
          <div>
            <h2>Positions</h2>
            <ul>
              {detail.positions.map((p, i) => (
                <li key={i}>
                  {p.owner} – {p.account} : {p.units}
                </li>
              ))}
            </ul>
          </div>
        )
      )}
    </div>
  );
}
