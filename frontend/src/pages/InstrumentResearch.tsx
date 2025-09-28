import { useEffect, useRef, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { useParams, Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useInstrumentHistory, updateCachedInstrumentHistory } from "../hooks/useInstrumentHistory";
import { InstrumentDetail, InstrumentPositionsTable } from "../components/InstrumentDetail";
import {
  confirmInstrumentMetadata,
  getNews,
  getScreener,
  listInstrumentMetadata,
  refreshInstrumentMetadata,
  updateInstrumentMetadata,
  type InstrumentMetadataRefreshResponse,
} from "../api";
import type { NewsItem, InstrumentMetadata, ScreenerResult } from "../types";
import EmptyState from "../components/EmptyState";
import { useConfig, SUPPORTED_CURRENCIES } from "../ConfigContext";
import surfaceStyles from "../styles/surface.module.css";
import { formatDateISO } from "../lib/date";
import { money, percent } from "../lib/money";
import { translateInstrumentType } from "../lib/instrumentType";

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

function normaliseInstrumentType(value: unknown) {
  if (typeof value !== "string") return undefined;
  const trimmed = value.trim();
  return trimmed || undefined;
}

function extractInstrumentType(
  value: Record<string, unknown> | null | undefined,
) {
  if (!value) return undefined;
  const camel = value["instrumentType"];
  if (typeof camel === "string") {
    const normalised = normaliseInstrumentType(camel);
    if (normalised) return normalised;
  }
  const snake = value["instrument_type"];
  if (typeof snake === "string") {
    const normalised = normaliseInstrumentType(snake);
    if (normalised) return normalised;
  }
  const assetClass = value["asset_class"];
  if (typeof assetClass === "string") {
    const normalised = normaliseInstrumentType(assetClass);
    if (normalised) return normalised;
  }
  return undefined;
}

const DEFAULT_INSTRUMENT_TYPES = [
  "Equity",
  "Bond",
  "Cash",
  "ETF",
  "Fund",
  "Investment Trust",
  "Real Estate",
];

function addInstrumentTypeOption(options: string[], value: string) {
  const normalised = normaliseInstrumentType(value);
  if (!normalised) return options;
  const lower = normalised.toLowerCase();
  if (options.some((entry) => entry.toLowerCase() === lower)) {
    return options;
  }
  return [...options, normalised].sort((a, b) =>
    a.localeCompare(b, undefined, { sensitivity: "base" }),
  );
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
  type MetadataState = {
    name: string;
    sector: string;
    instrumentType: string;
    currency: string;
  };
  type MetadataOverrides = {
    name: boolean;
    sector: boolean;
    instrumentType: boolean;
    currency: boolean;
  };
  type RefreshPreviewState = {
    metadata: MetadataState;
    changes: InstrumentMetadataRefreshResponse["changes"];
  };
  const [metadata, setMetadata] = useState<MetadataState>({
    name: "",
    sector: "",
    instrumentType: "",
    currency: "",
  });
  const [formValues, setFormValues] = useState<MetadataState>({
    name: "",
    sector: "",
    instrumentType: "",
    currency: "",
  });
  const [metadataOverrides, setMetadataOverrides] = useState<MetadataOverrides>({
    name: false,
    sector: false,
    instrumentType: false,
    currency: false,
  });
  const [isEditingMetadata, setIsEditingMetadata] = useState(false);
  const isEditingMetadataRef = useRef(isEditingMetadata);
  const metadataOverridesRef = useRef(metadataOverrides);
  const [metadataSaving, setMetadataSaving] = useState(false);
  const [metadataStatus, setMetadataStatus] = useState<
    { kind: "success" | "error"; text: string } | null
  >(null);
  const [refreshPreview, setRefreshPreview] = useState<RefreshPreviewState | null>(null);
  const [refreshContext, setRefreshContext] = useState<
    { form: MetadataState; wasEditing: boolean } | null
  >(null);
  const [refreshingMetadata, setRefreshingMetadata] = useState(false);
  const [confirmingRefresh, setConfirmingRefresh] = useState(false);
  const [refreshError, setRefreshError] = useState<string | null>(null);
  const [sectorOptions, setSectorOptions] = useState<string[]>([]);
  const [instrumentTypeOptions, setInstrumentTypeOptions] = useState<string[]>(
    DEFAULT_INSTRUMENT_TYPES,
  );
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

  const metadataStateFromResponse = (
    payload: InstrumentMetadataRefreshResponse["metadata"],
  ): MetadataState => {
    const record = (payload ?? {}) as Record<string, unknown>;
    const rawName = typeof record.name === "string" ? record.name : "";
    const rawSector = typeof record.sector === "string" ? record.sector : "";
    const rawCurrency = typeof record.currency === "string" ? record.currency : "";
    const instrumentTypeCandidates = [
      record["instrumentType"],
      record["instrument_type"],
      record["asset_class"],
    ];
    const candidate = instrumentTypeCandidates.find(
      (value): value is string => typeof value === "string",
    );
    const normalisedType = normaliseInstrumentType(candidate);
    const normalisedCurrency = normaliseUppercase(rawCurrency);
    return {
      name: normaliseOptional(rawName) ?? rawName ?? "",
      sector: normaliseOptional(rawSector) ?? rawSector ?? "",
      instrumentType: normalisedType ?? (candidate ?? ""),
      currency:
        normalisedCurrency ?? (rawCurrency ? rawCurrency.toUpperCase() : ""),
    };
  };

  useEffect(() => {
    setInstrumentExchange(initialExchange);
    setIsEditingMetadata(false);
    setMetadataSaving(false);
    setMetadataStatus(null);
    setRefreshPreview(null);
    setRefreshContext(null);
    setRefreshError(null);
    setRefreshingMetadata(false);
    setConfirmingRefresh(false);
    setMetadata({ name: "", sector: "", instrumentType: "", currency: "" });
    setFormValues({
      name: "",
      sector: "",
      instrumentType: "",
      currency: "",
    });
    setMetadataOverrides({
      name: false,
      sector: false,
      instrumentType: false,
      currency: false,
    });
    setSectorOptions([]);
    setInstrumentTypeOptions(DEFAULT_INSTRUMENT_TYPES);
    setOverviewHistoryDays(0);
  }, [tkr, initialExchange]);

  useEffect(() => {
    isEditingMetadataRef.current = isEditingMetadata;
  }, [isEditingMetadata]);

  useEffect(() => {
    metadataOverridesRef.current = metadataOverrides;
  }, [metadataOverrides]);

  useEffect(() => {
    if (!detail) return;
    const name = normaliseOptional(detail.name);
    const sector = normaliseOptional(detail.sector);
    const normalizedBaseCurrency =
      detail && typeof detail.base_currency === "string"
        ? normaliseUppercase(detail.base_currency)
        : undefined;
    const currency =
      normalizedBaseCurrency ?? normaliseUppercase(detail?.currency ?? undefined);
    const detailRecord =
      detail && typeof detail === "object"
        ? (detail as unknown as Record<string, unknown>)
        : null;
    const detailInstrumentType = extractInstrumentType(detailRecord);
    const overrides = metadataOverridesRef.current;
    let nextMetadata: MetadataState | null = null;
    setMetadata((prev) => {
      const next: MetadataState = {
        name: overrides.name ? prev.name : name ?? prev.name ?? "",
        sector: overrides.sector ? prev.sector : sector ?? prev.sector ?? "",
        instrumentType: overrides.instrumentType
          ? prev.instrumentType
          : detailInstrumentType ?? prev.instrumentType ?? "",
        currency: overrides.currency ? prev.currency : currency ?? prev.currency ?? "",
      };
      nextMetadata = next;
      return next;
    });
    if (!isEditingMetadata && nextMetadata) {
      setFormValues(nextMetadata);
    }
    if (detailInstrumentType) {
      setInstrumentTypeOptions((prev) =>
        addInstrumentTypeOption(prev, detailInstrumentType),
      );
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
        const instrumentTypes = new Map<string, string>();
        DEFAULT_INSTRUMENT_TYPES.forEach((type) =>
          instrumentTypes.set(type.toLowerCase(), type),
        );
        let matched: InstrumentMetadata | null = null;
        const target = tkr.toUpperCase();
        const base = baseTicker.toUpperCase();
        for (const entry of catalogue ?? []) {
          if (!entry) continue;
          if (typeof entry.sector === "string") {
            const trimmed = entry.sector.trim();
            if (trimmed) sectors.add(trimmed);
          }
          const entryInstrumentType = normaliseInstrumentType(
            (entry as { instrumentType?: unknown }).instrumentType ??
              (entry as { instrument_type?: unknown }).instrument_type,
          );
          if (entryInstrumentType) {
            const key = entryInstrumentType.toLowerCase();
            if (!instrumentTypes.has(key)) {
              instrumentTypes.set(key, entryInstrumentType);
            }
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
        setInstrumentTypeOptions(
          Array.from(instrumentTypes.values()).sort((a, b) =>
            a.localeCompare(b, undefined, { sensitivity: "base" }),
          ),
        );
        if (matched) {
          const name = normaliseOptional(matched.name) ?? matched.name;
          const sector = normaliseOptional(matched.sector);
          const currency = normaliseUppercase(matched.currency);
          const metaInstrumentType = normaliseInstrumentType(
            (matched as { instrumentType?: unknown }).instrumentType ??
              (matched as { instrument_type?: unknown }).instrument_type,
          );
          const overrides = metadataOverridesRef.current;
          const hasName = typeof name === "string" && name.length > 0;
          const hasSector = typeof sector === "string" && sector.length > 0;
          const hasInstrumentType =
            typeof metaInstrumentType === "string" && metaInstrumentType.length > 0;
          const hasCurrency = typeof currency === "string" && currency.length > 0;
          let nextMetadata: MetadataState | null = null;
          setMetadata((prev) => {
            const next: MetadataState = {
              name: overrides.name ? prev.name : hasName ? name : prev.name || "",
              sector: overrides.sector
                ? prev.sector
                : hasSector
                  ? sector
                  : prev.sector || "",
              instrumentType: overrides.instrumentType
                ? prev.instrumentType
                : hasInstrumentType
                  ? metaInstrumentType
                  : prev.instrumentType || "",
              currency: overrides.currency
                ? prev.currency
                : hasCurrency
                  ? currency
                  : prev.currency || "",
            };
            nextMetadata = next;
            return next;
          });
          setMetadataOverrides((prev) => ({
            name: prev.name || hasName,
            sector: prev.sector || hasSector,
            instrumentType: prev.instrumentType || hasInstrumentType,
            currency: prev.currency || hasCurrency,
          }));
          if (!isEditingMetadataRef.current && nextMetadata) {
            setFormValues(nextMetadata);
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
    setRefreshPreview(null);
    setRefreshContext(null);
    setRefreshError(null);
    setFormValues(metadata);
    setMetadataStatus(null);
    setIsEditingMetadata(true);
  };

  const handleCancelEditing = () => {
    setRefreshPreview(null);
    setRefreshContext(null);
    setRefreshError(null);
    setFormValues(metadata);
    setIsEditingMetadata(false);
    setMetadataStatus((prev) => (prev?.kind === "success" ? prev : null));
  };

  const deriveExchangeForActions = () => {
    const fromState = normaliseUppercase(instrumentExchange);
    if (fromState) return fromState;
    const initial = normaliseUppercase(initialExchange);
    if (initial) return initial;
    if (tkr.includes(".")) {
      const [, exch] = tkr.split(".", 2);
      const normalised = normaliseUppercase(exch);
      if (normalised) return normalised;
    }
    return "";
  };

  const handleRefreshMetadata = async () => {
    if (refreshingMetadata || confirmingRefresh) return;
    const exchange = deriveExchangeForActions();
    if (!baseTicker || !exchange) {
      setRefreshError(t("instrumentDetail.metadataMissingExchange"));
      return;
    }
    setRefreshError(null);
    setRefreshingMetadata(true);
    try {
      const preview = await refreshInstrumentMetadata(baseTicker, exchange);
      const previewMetadata = metadataStateFromResponse(preview.metadata);
      setRefreshContext({ form: { ...formValues }, wasEditing: isEditingMetadata });
      setFormValues(previewMetadata);
      setRefreshPreview({ metadata: previewMetadata, changes: preview.changes || {} });
      setIsEditingMetadata(true);
      setMetadataStatus(null);
    } catch (err) {
      console.error(err);
      const message = err instanceof Error ? err.message : String(err);
      setRefreshError(`${t("instrumentDetail.refreshError")} ${message}`);
    } finally {
      setRefreshingMetadata(false);
    }
  };

  const handleConfirmRefresh = async () => {
    if (!refreshPreview || confirmingRefresh) return;
    const exchange = deriveExchangeForActions();
    if (!baseTicker || !exchange) {
      setRefreshError(t("instrumentDetail.metadataMissingExchange"));
      return;
    }
    setConfirmingRefresh(true);
    setRefreshError(null);
    setMetadataStatus(null);
    try {
      const result = await confirmInstrumentMetadata(baseTicker, exchange);
      const next = metadataStateFromResponse(result.metadata);
      setMetadata(next);
      setMetadataOverrides({ name: true, sector: true, instrumentType: true, currency: true });
      setFormValues(next);
      setInstrumentExchange(exchange);
      setIsEditingMetadata(false);
      setRefreshPreview(null);
      setRefreshContext(null);
      updateCachedInstrumentHistory(tkr, (cached) => {
        cached.name = next.name;
        cached.sector = next.sector;
        cached.currency = next.currency;
        cached.instrument_type = next.instrumentType || null;
        (cached as unknown as Record<string, unknown>).instrumentType =
          next.instrumentType || null;
      });
      if (next.sector) {
        setSectorOptions((prev) => {
          if (prev.some((entry) => entry.toUpperCase() === next.sector.toUpperCase())) {
            return prev;
          }
          return [...prev, next.sector].sort((a, b) =>
            a.localeCompare(b, undefined, { sensitivity: "base" }),
          );
        });
      }
      if (next.instrumentType) {
        setInstrumentTypeOptions((prev) => addInstrumentTypeOption(prev, next.instrumentType));
      }
      setMetadataStatus({ kind: "success", text: t("instrumentDetail.refreshSuccess") });
    } catch (err) {
      console.error(err);
      const message = err instanceof Error ? err.message : String(err);
      setRefreshError(`${t("instrumentDetail.refreshError")} ${message}`);
    } finally {
      setConfirmingRefresh(false);
    }
  };

  const handleCancelRefresh = () => {
    const previous = refreshContext;
    if (previous) {
      setFormValues(previous.form);
      setIsEditingMetadata(previous.wasEditing);
    } else {
      setFormValues(metadata);
      setIsEditingMetadata(false);
    }
    setRefreshPreview(null);
    setRefreshContext(null);
    setRefreshError(null);
  };

  const handleSaveMetadata = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!isEditingMetadata) return;
    const trimmedName = formValues.name.trim();
    const trimmedSector = formValues.sector.trim();
    const trimmedInstrumentType = formValues.instrumentType.trim();
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
        instrument_type: trimmedInstrumentType || null,
        instrumentType: trimmedInstrumentType || null,
      };
      await updateInstrumentMetadata(baseTicker, exchange, payload);
      setMetadata({
        name: trimmedName,
        sector: trimmedSector,
        instrumentType: trimmedInstrumentType,
        currency: selectedCurrency,
      });
      setMetadataOverrides({
        name: true,
        sector: true,
        instrumentType: true,
        currency: true,
      });
      setFormValues({
        name: trimmedName,
        sector: trimmedSector,
        instrumentType: trimmedInstrumentType,
        currency: selectedCurrency,
      });
      setInstrumentExchange(exchange);
      setIsEditingMetadata(false);
      updateCachedInstrumentHistory(tkr, (cached) => {
        cached.name = trimmedName;
        cached.sector = trimmedSector;
        cached.currency = selectedCurrency;
        cached.instrument_type = trimmedInstrumentType || null;
        (cached as unknown as Record<string, unknown>).instrumentType =
          trimmedInstrumentType || null;
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
      if (trimmedInstrumentType) {
        setInstrumentTypeOptions((prev) =>
          addInstrumentTypeOption(prev, trimmedInstrumentType),
        );
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
  const fallbackCurrency = detail
    ? (typeof detail.base_currency === "string"
        ? normaliseUppercase(detail.base_currency)
        : undefined) ?? normaliseUppercase(detail.currency)
    : undefined;
  const displayName = metadata.name || detail?.name || null;
  const displaySector = metadata.sector || fallbackSector || "";
  const displayCurrency = metadata.currency || fallbackCurrency || "";
  const fundamentalsCurrency =
    (typeof detail?.base_currency === "string" && detail.base_currency) ||
    displayCurrency ||
    baseCurrency ||
    "USD";
  const detailRecordForDisplay =
    detail && typeof detail === "object"
      ? (detail as unknown as Record<string, unknown>)
      : null;
  const detailInstrumentType = extractInstrumentType(detailRecordForDisplay);
  const instrumentType = metadata.instrumentType || detailInstrumentType || null;
  const displayInstrumentType = instrumentType || "";
  const positions = Array.isArray(detail?.positions) ? detail.positions : [];
  const instrumentTypeSelectOptions = (() => {
    const entries = new Map<string, string>();
    instrumentTypeOptions.forEach((value) => {
      const normalised = normaliseInstrumentType(value);
      if (!normalised) return;
      entries.set(normalised.toLowerCase(), normalised);
    });
    const current = normaliseInstrumentType(formValues.instrumentType);
    if (current) entries.set(current.toLowerCase(), current);
    return Array.from(entries.values()).sort((a, b) =>
      a.localeCompare(b, undefined, { sensitivity: "base" }),
    );
  })();
  const metadataInputsDisabled =
    metadataSaving || refreshingMetadata || confirmingRefresh || !!refreshPreview;
  const exchangeForActions = deriveExchangeForActions();

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
          <div
            style={{
              display: "flex",
              gap: "0.5rem",
              flexWrap: "wrap",
              alignItems: "center",
            }}
          >
            <button
              type="button"
              onClick={handleRefreshMetadata}
              disabled={
                refreshingMetadata ||
                confirmingRefresh ||
                metadataSaving ||
                !!refreshPreview ||
                !baseTicker ||
                !exchangeForActions
              }
            >
              {refreshingMetadata
                ? `${t("instrumentDetail.refresh")}…`
                : t("instrumentDetail.refresh")}
            </button>
            {refreshPreview ? (
              <>
                <button
                  type="button"
                  onClick={handleConfirmRefresh}
                  disabled={confirmingRefresh || refreshingMetadata}
                >
                  {confirmingRefresh
                    ? `${t("instrumentDetail.refreshConfirm")}…`
                    : t("instrumentDetail.refreshConfirm")}
                </button>
                <button
                  type="button"
                  onClick={handleCancelRefresh}
                  disabled={confirmingRefresh || refreshingMetadata}
                >
                  {t("instrumentDetail.refreshCancel")}
                </button>
              </>
            ) : isEditingMetadata ? (
              <>
                <button type="submit" disabled={metadataSaving}>
                  {t("instrumentDetail.save")}
                </button>
                <button
                  type="button"
                  onClick={handleCancelEditing}
                  disabled={metadataSaving}
                >
                  {t("instrumentDetail.cancel")}
                </button>
              </>
            ) : (
              <button type="button" onClick={handleStartEditing}>
                {t("instrumentDetail.edit")}
              </button>
            )}
          </div>
        </div>
        {refreshError && (
          <div style={{ marginBottom: "0.5rem", color: "red" }}>{refreshError}</div>
        )}
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
        {refreshPreview && (
          <div
            style={{
              marginBottom: "0.75rem",
              padding: "0.75rem",
              border: "1px solid #ddd",
              borderRadius: "4px",
              background: "#f7f9fc",
            }}
          >
            <strong>{t("instrumentDetail.refreshPreviewTitle")}</strong>
            <p style={{ margin: "0.25rem 0 0.5rem" }}>
              {t("instrumentDetail.refreshPreviewDescription")}
            </p>
            {(() => {
              const canonicalChanges = new Map<string, { from: unknown; to: unknown }>();
              const mappings: Record<string, string> = {
                name: "name",
                sector: "sector",
                currency: "currency",
                instrument_type: "instrument_type",
                instrumentType: "instrument_type",
              };
              Object.entries(refreshPreview.changes ?? {}).forEach(([key, value]) => {
                const mapped = mappings[key];
                if (!mapped) return;
                canonicalChanges.set(mapped, value);
              });
              const entries = Array.from(canonicalChanges.entries());
              if (!entries.length) {
                return (
                  <p style={{ margin: 0 }}>
                    {t("instrumentDetail.refreshNoChanges")}
                  </p>
                );
              }
              const formatValue = (value: unknown) => {
                if (value == null) return "—";
                if (typeof value === "string" && !value.trim()) return "—";
                return String(value);
              };
              const labelMap: Record<string, string> = {
                name: t("instrumentDetail.nameLabel"),
                sector: t("instrumentDetail.sectorLabel"),
                currency: t("instrumentDetail.currencyLabel"),
                instrument_type: t("instrumentDetail.instrumentTypeLabel", {
                  defaultValue: "Instrument type",
                }),
              };
              return (
                <ul style={{ margin: 0, paddingLeft: "1.1rem" }}>
                  {entries.map(([field, change]) => (
                    <li key={field} style={{ marginBottom: "0.25rem" }}>
                      <span style={{ fontWeight: 600 }}>
                        {labelMap[field] ?? field}:
                      </span>{" "}
                      {formatValue(change.from)} → {formatValue(change.to)}
                    </li>
                  ))}
                </ul>
              );
            })()}
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
                  disabled={metadataInputsDisabled}
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
                  disabled={metadataInputsDisabled}
                />
              </label>
            ) : (
              <span>
                {t("instrumentDetail.sectorLabel")}: {displaySector || "—"}
              </span>
            )}
          </li>
          <li style={{ marginBottom: "0.5rem" }}>
            {isEditingMetadata ? (
              <label htmlFor="instrument-type" style={{ display: "block" }}>
                {t("instrumentDetail.instrumentTypeLabel", {
                  defaultValue: "Instrument type",
                })}
                <select
                  id="instrument-type"
                  value={formValues.instrumentType}
                  onChange={(e) => updateFormField("instrumentType")(e.target.value)}
                  style={{ display: "block", marginTop: "0.25rem" }}
                  disabled={metadataInputsDisabled}
                >
                  <option value="">
                    {t("instrumentDetail.instrumentTypePlaceholder", {
                      defaultValue: "Select a type",
                    })}
                  </option>
                  {instrumentTypeSelectOptions.map((type) => (
                    <option key={type} value={type}>
                      {translateInstrumentType(t, type)}
                    </option>
                  ))}
                </select>
              </label>
            ) : (
              <span>
                {t("instrumentDetail.instrumentTypeLabel", {
                  defaultValue: "Instrument type",
                })}
                : {displayInstrumentType
                  ? translateInstrumentType(t, displayInstrumentType)
                  : "—"}
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
                  disabled={metadataInputsDisabled}
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
