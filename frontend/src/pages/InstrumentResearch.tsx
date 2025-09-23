import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { useParams, Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useInstrumentHistory, getCachedInstrumentHistory } from "../hooks/useInstrumentHistory";
import { InstrumentPositionsTable } from "../components/InstrumentDetail";
import {
  getNews,
  getQuotes,
  getScreener,
  listInstrumentMetadata,
  updateInstrumentMetadata,
} from "../api";
import type {
  NewsItem,
  InstrumentMetadata,
  QuoteRow,
  ScreenerResult,
} from "../types";
import EmptyState from "../components/EmptyState";
import { useConfig, SUPPORTED_CURRENCIES } from "../ConfigContext";
import { formatDateISO } from "../lib/date";

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
  const { t, i18n } = useTranslation();
  const tkr = ticker && /^[A-Za-z0-9.-]{1,10}$/.test(ticker) ? ticker : "";
  const tickerParts = tkr.split(".", 2);
  const baseTicker = tickerParts[0] ?? "";
  const initialExchange = tickerParts.length > 1 ? tickerParts[1] ?? "" : "";
  const { tabs, disabledTabs } = useConfig();
  const {
    data: detail,
    loading: detailLoading,
    error: detailError,
  } = useInstrumentHistory(tkr, 365);
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
    "overview" | "timeseries" | "positions" | "news" | "fundamentals"
  >("overview");
  const [fundamentals, setFundamentals] = useState<ScreenerResult | null>(null);
  const [fundamentalsLoading, setFundamentalsLoading] = useState(() => !!tkr);
  const [fundamentalsError, setFundamentalsError] = useState<string | null>(null);
  const [quote, setQuote] = useState<QuoteRow | null>(null);
  const [quoteLoading, setQuoteLoading] = useState(() => !!tkr);
  const [quoteError, setQuoteError] = useState<string | null>(null);

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

  useEffect(() => {
    if (!tkr) return;
    let cancelled = false;
    const controller = new AbortController();
    setFundamentalsLoading(true);
    setFundamentalsError(null);
    setFundamentals(null);
    getScreener([tkr], {}, controller.signal)
      .then((results) => {
        if (cancelled) return;
        setFundamentals(results?.[0] ?? null);
      })
      .catch((err) => {
        if (cancelled) return;
        const error = err as { name?: string } | null | undefined;
        if (error?.name === "AbortError") {
          return;
        }
        console.error(err);
        setFundamentals(null);
        setFundamentalsError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        if (cancelled) return;
        setFundamentalsLoading(false);
      });
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [tkr]);

  useEffect(() => {
    if (!tkr) return;
    let cancelled = false;
    const controller = new AbortController();
    setQuoteLoading(true);
    setQuoteError(null);
    setQuote(null);
    getQuotes([tkr], controller.signal)
      .then((rows) => {
        if (cancelled) return;
        setQuote(rows?.[0] ?? null);
      })
      .catch((err) => {
        if (cancelled) return;
        const error = err as { name?: string } | null | undefined;
        if (error?.name === "AbortError") {
          return;
        }
        console.error(err);
        setQuote(null);
        setQuoteError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        if (cancelled) return;
        setQuoteLoading(false);
      });
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [tkr]);

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
  const instrumentType =
    detail && typeof (detail as { instrument_type?: unknown }).instrument_type === "string"
      ? ((detail as { instrument_type?: string }).instrument_type ?? null)
      : null;
  const positions = Array.isArray(detail?.positions) ? detail.positions : [];

  const tabOptions: { id: typeof activeTab; label: string }[] = [
    { id: "overview", label: "Overview" },
    { id: "timeseries", label: "Timeseries" },
    { id: "positions", label: "Positions" },
    { id: "news", label: "News" },
    { id: "fundamentals", label: "Fundamentals" },
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

      {(detailError || activeTab !== "fundamentals") && (
        <div style={{ marginBottom: "1rem" }}>
          {detailError && <div style={{ color: "red" }}>{detailError.message}</div>}
          {activeTab !== "fundamentals" && (
            <>
              {fundamentalsLoading && <div>Loading metrics...</div>}
              {fundamentalsError && (
                <div style={{ color: "red" }}>{fundamentalsError}</div>
              )}
              {quoteLoading && <div>Loading quote...</div>}
              {quoteError && <div style={{ color: "red" }}>{quoteError}</div>}
            </>
          )}
        </div>
      )}

      {activeTab === "timeseries" && (
        <div style={{ marginBottom: "2rem" }}>
          {detailLoading ? (
            <div>Loading timeseries...</div>
          ) : detailError ? (
            <div style={{ color: "red" }}>{detailError.message}</div>
          ) : (() => {
              const rawPrices = Array.isArray(detail?.prices)
                ? (detail?.prices as Record<string, unknown>[])
                : [];
              const rows = rawPrices
                .filter((entry): entry is Record<string, unknown> =>
                  entry != null,
                )
                .slice(-60)
                .reverse();
              if (rows.length === 0) {
                return <EmptyState message="No price history available" />;
              }
              const numberFormatter = new Intl.NumberFormat(i18n.language, {
                maximumFractionDigits: 2,
              });
              const formatPrice = (value: unknown) => {
                if (typeof value !== "number" || Number.isNaN(value)) {
                  return "—";
                }
                return numberFormatter.format(value);
              };
              const priceHeading = displayCurrency
                ? `Close (${displayCurrency})`
                : "Close";
              return (
                <div>
                  <h2 style={{ marginTop: 0 }}>Recent Prices</h2>
                  <table style={{ width: "100%", borderCollapse: "collapse" }}>
                    <thead>
                      <tr>
                        <th
                          scope="col"
                          style={{
                            textAlign: "left",
                            padding: "0.25rem 0.5rem 0.25rem 0",
                            borderBottom: "1px solid #eee",
                          }}
                        >
                          Date
                        </th>
                        <th
                          scope="col"
                          style={{
                            textAlign: "right",
                            padding: "0.25rem 0",
                            borderBottom: "1px solid #eee",
                          }}
                        >
                          {priceHeading}
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((row, index) => {
                        const rawDate = row.date as string | undefined;
                        let formattedDate = "—";
                        if (rawDate) {
                          const parsed = new Date(rawDate);
                          formattedDate = Number.isNaN(parsed.getTime())
                            ? rawDate
                            : formatDateISO(parsed);
                        }
                        const closeValue =
                          typeof row.close_gbp === "number"
                            ? row.close_gbp
                            : typeof row.close === "number"
                            ? row.close
                            : null;
                        return (
                          <tr key={rawDate ?? index}>
                            <td
                              style={{
                                padding: "0.25rem 0.5rem 0.25rem 0",
                                borderBottom: "1px solid #eee",
                              }}
                            >
                              {formattedDate}
                            </td>
                            <td
                              style={{
                                padding: "0.25rem 0",
                                textAlign: "right",
                                borderBottom: "1px solid #eee",
                              }}
                            >
                              {formatPrice(closeValue)}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              );
            })()}
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

      {(() => {
        const visible = activeTab === "fundamentals";
        const formatNumber = (
          value: number | null | undefined,
          options: Intl.NumberFormatOptions = { maximumFractionDigits: 2 },
        ) => {
          if (value == null || Number.isNaN(value)) return "—";
          try {
            return new Intl.NumberFormat(i18n.language, options).format(value);
          } catch (err) {
            console.error(err);
            return String(value);
          }
        };
        const formatSignedNumber = (
          value: number | null | undefined,
          options: Intl.NumberFormatOptions = { maximumFractionDigits: 2 },
        ) => {
          if (value == null || Number.isNaN(value)) return "—";
          return formatNumber(value, { ...options, signDisplay: "always" });
        };
        const formatDateTime = (value: string | null) => {
          if (!value) return "—";
          const date = new Date(value);
          if (Number.isNaN(date.getTime())) return "—";
          return new Intl.DateTimeFormat(i18n.language, {
            dateStyle: "medium",
            timeStyle: "short",
          }).format(date);
        };
        const fundamentalsRows: {
          label: string;
          value: number | null | undefined;
          options?: Intl.NumberFormatOptions;
        }[] = [
          { label: "PEG Ratio", value: fundamentals?.peg_ratio },
          { label: "P/E Ratio", value: fundamentals?.pe_ratio },
          { label: "Debt/Equity", value: fundamentals?.de_ratio },
          { label: "LT Debt/Equity", value: fundamentals?.lt_de_ratio },
          { label: "Interest Coverage", value: fundamentals?.interest_coverage },
          { label: "Current Ratio", value: fundamentals?.current_ratio },
          { label: "Quick Ratio", value: fundamentals?.quick_ratio },
          { label: "FCF", value: fundamentals?.fcf, options: { maximumFractionDigits: 0 } },
          { label: "EPS", value: fundamentals?.eps },
          { label: "Gross Margin", value: fundamentals?.gross_margin },
          { label: "Operating Margin", value: fundamentals?.operating_margin },
          { label: "Net Margin", value: fundamentals?.net_margin },
          { label: "EBITDA Margin", value: fundamentals?.ebitda_margin },
          { label: "ROA", value: fundamentals?.roa },
          { label: "ROE", value: fundamentals?.roe },
          { label: "ROI", value: fundamentals?.roi },
          { label: "Dividend Yield", value: fundamentals?.dividend_yield },
          {
            label: "Dividend Payout Ratio",
            value: fundamentals?.dividend_payout_ratio,
          },
          { label: "Beta", value: fundamentals?.beta },
          {
            label: "Shares Outstanding",
            value: fundamentals?.shares_outstanding,
            options: { maximumFractionDigits: 0 },
          },
          {
            label: "Float Shares",
            value: fundamentals?.float_shares,
            options: { maximumFractionDigits: 0 },
          },
          {
            label: "Market Cap",
            value: fundamentals?.market_cap,
            options: { maximumFractionDigits: 0 },
          },
          { label: "52 Week High", value: fundamentals?.high_52w },
          { label: "52 Week Low", value: fundamentals?.low_52w },
          {
            label: "Average Volume",
            value: fundamentals?.avg_volume,
            options: { maximumFractionDigits: 0 },
          },
        ];
          const quoteRows = [
            {
              label: "Price",
              value:
                quote?.last != null
                  ? `${formatNumber(quote.last, { maximumFractionDigits: 2 })}${
                      displayCurrency ? ` ${displayCurrency}` : ""
                    }`
                  : "—",
            },
            {
              label: "Change",
              value:
                quote?.change != null
                  ? formatSignedNumber(quote.change, { maximumFractionDigits: 2 })
                  : "—",
            },
            {
              label: "Change %",
              value:
                quote?.changePct != null
                  ? `${formatSignedNumber(quote.changePct, {
                      maximumFractionDigits: 2,
                    })}%`
                  : "—",
            },
            {
              label: "Open",
              value: formatNumber(quote?.open),
            },
            {
              label: "High",
              value: formatNumber(quote?.high),
            },
            {
              label: "Low",
              value: formatNumber(quote?.low),
            },
            {
              label: "Volume",
              value: formatNumber(quote?.volume, { maximumFractionDigits: 0 }),
            },
            {
              label: "Market Time",
              value: formatDateTime(quote?.marketTime ?? null),
            },
            {
              label: "Market State",
              value: quote?.marketState ?? "—",
            },
          ];
          const fundamentalsTable = (
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <tbody>
                {fundamentalsRows.map((row) => (
                  <tr key={row.label}>
                    <th
                      scope="row"
                      style={{
                        textAlign: "left",
                        padding: "0.25rem 0.5rem 0.25rem 0",
                        borderBottom: "1px solid #eee",
                        fontWeight: 600,
                        width: "50%",
                      }}
                    >
                      {row.label}
                    </th>
                    <td
                      style={{
                        textAlign: "right",
                        padding: "0.25rem 0",
                        borderBottom: "1px solid #eee",
                      }}
                    >
                      {formatNumber(row.value, row.options)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          );
          const shouldShowFundamentalsTable =
            !!fundamentals && !fundamentalsLoading && !fundamentalsError;
          return (
            <div
              style={{
                display: visible ? "grid" : "none",
                gap: "1.5rem",
              }}
              aria-hidden={!visible}
            >
              <section>
                <h2 style={{ marginTop: 0 }}>Quote Summary</h2>
                {visible ? (
                  quoteLoading ? (
                    <div>Loading quote...</div>
                  ) : quoteError ? (
                    <div style={{ color: "red" }}>{quoteError}</div>
                  ) : !quote ? (
                    <EmptyState message="Quote unavailable" />
                  ) : (
                    <table style={{ width: "100%", borderCollapse: "collapse" }}>
                      <tbody>
                        {quoteRows.map((row) => (
                          <tr key={row.label}>
                            <th
                              scope="row"
                              style={{
                                textAlign: "left",
                                padding: "0.25rem 0.5rem 0.25rem 0",
                                borderBottom: "1px solid #eee",
                                fontWeight: 600,
                                width: "50%",
                              }}
                            >
                              {row.label}
                            </th>
                            <td
                              style={{
                                textAlign: "right",
                                padding: "0.25rem 0",
                                borderBottom: "1px solid #eee",
                              }}
                            >
                              {row.value}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )
                ) : null}
              </section>
              <section>
                <h2 style={{ marginTop: 0 }}>Fundamentals</h2>
                {visible ? (
                  fundamentalsLoading ? (
                    <div>Loading metrics...</div>
                  ) : fundamentalsError ? (
                    <div style={{ color: "red" }}>{fundamentalsError}</div>
                  ) : !fundamentals ? (
                    <EmptyState message="No fundamentals available" />
                  ) : (
                    fundamentalsTable
                  )
                ) : shouldShowFundamentalsTable ? (
                  fundamentalsTable
                ) : null}
              </section>
            </div>
          );
      })()}
    </div>
  );
}
