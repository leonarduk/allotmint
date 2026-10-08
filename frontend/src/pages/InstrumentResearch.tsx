import { useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { useParams, Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  invalidateInstrumentHistory,
  useInstrumentHistory,
  updateCachedInstrumentHistory,
} from "../hooks/useInstrumentHistory";
import { InstrumentDetail, InstrumentPositionsTable } from "../components/InstrumentDetail";
import { InstrumentTradeSection } from "../components/InstrumentTradeSection";
import { InstrumentValuationPanel } from "../components/InstrumentValuationPanel";
import { InstrumentTechnicalsPanel } from "../components/InstrumentTechnicalsPanel";
import { InstrumentAllocationPanel } from "../components/LookThrough";
import {
  confirmInstrumentMetadata,
  createInstrumentMetadata,
  getNews,
  getScreener,
  listInstrumentMetadata,
  refreshInstrumentMetadata,
  updateInstrumentMetadata,
  type InstrumentMetadataRefreshResponse,
} from "../api";
import type { NewsItem, InstrumentMetadata, ScreenerResult } from "../types";
import EmptyState from "../components/EmptyState";
import { InstrumentSearchBar } from "../components/InstrumentSearchBar";
import { DeleteSeriesButton } from "../components/DeleteSeriesButton";
import { RefreshPricesButton } from "../components/RefreshPricesButton";
import InstrumentAlertsSection from "../components/InstrumentAlertsSection";
import InstrumentNotesSection from "../components/InstrumentNotesSection";
import { useInstrumentAlertCount } from "../hooks/useInstrumentAlertCount";
import { useInstrumentNoteCount } from "../hooks/useInstrumentNoteCount";
import { useConfig, SUPPORTED_CURRENCIES } from "../ConfigContext";
import surfaceStyles from "../styles/surface.module.css";
import { formatDateISO, localDateISO } from "../lib/date";
import { money, normalizeDisplayCurrency, percent, quotedPrice } from "../lib/money";
import { translateInstrumentType } from "../lib/instrumentType";
import { completeTrackedChore } from "../choreCompletion";
import {
  buildInvestingComUrl,
  buildJustEtfUrl,
  buildMorningstarUrl,
} from "../utils/urlUtils";
import { InstrumentIdentifiers } from "../components/InstrumentIdentifiers";
import { useMorningstarId } from "../hooks/useMorningstarId";
import { useLiveQuotes } from "../hooks/useLiveQuotes";

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

// Two-letter country, nine alphanumerics, one check digit.
const ISIN_PATTERN = /^[A-Z]{2}[A-Z0-9]{9}[0-9]$/;

function errorStatus(err: unknown) {
  return (err as { status?: number } | null)?.status;
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

// Exchange-traded products justETF profiles by ISIN (ETCs such as
// physical gold share its etf-profile page).
const JUSTETF_INSTRUMENT_TYPES = new Set(["ETF", "ETC", "ETN"]);

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

function sortNewsByPublishedAtDesc(items: NewsItem[]): NewsItem[] {
  return [...items].sort((a, b) => (b.published_at ?? "").localeCompare(a.published_at ?? ""));
}

type DisplayPrice = {
  close: number;
  currency: string;
  date: string | null;
};

function resolveDisplayPrice(
  price: Record<string, unknown>,
  nativeCurrency: string | undefined,
  reportingCurrency: string | undefined,
): DisplayPrice | null {
  const nativeClose = typeof price.close === "number" && Number.isFinite(price.close)
    ? price.close
    : null;
  const reportingClose =
    typeof price.close_gbp === "number" && Number.isFinite(price.close_gbp)
      ? price.close_gbp
      : typeof price.close_usd === "number" && Number.isFinite(price.close_usd)
        ? price.close_usd
        : null;
  const normalizedNativeCurrency = normaliseUppercase(nativeCurrency);
  const normalizedReportingCurrency = normaliseUppercase(reportingCurrency);
  // Discriminate on the DATA, not on a currency-code string: the backend's
  // top-level `currency` field on /instrument/ is hardcoded to the
  // reporting currency whenever a close_gbp column exists (routes/
  // instrument.py ~502-515), which is nearly always, so it cannot say what
  // `close` is actually quoted in (#7219). What the numbers themselves
  // reveal can be trusted: if `close` and the reporting close carry the
  // same value, `close` IS already the reporting currency; if they differ,
  // `close` is still native and must be labelled with the instrument's own
  // declared/quote currency (from metadata) instead of the reporting one.
  //
  // The "same value" check uses a RELATIVE tolerance, not an absolute one.
  // When close IS already the reporting currency, the backend assigns it
  // verbatim (df["Close_gbp"] = df["Close"], routes/instrument.py ~425/441)
  // -- the two floats are bit-identical, so this only needs to absorb
  // genuine float noise. A fixed absolute epsilon (e.g. 0.005) instead
  // opens a false-positive band that misfires whenever
  // |close| * |1 - rate| falls under it -- at a perfectly ordinary
  // EUR/GBP rate of ~0.92, any EUR instrument priced under ~6 cents would
  // be wrongly treated as "already GBP" and mislabelled.
  const closeMatchesReporting =
    nativeClose != null &&
    reportingClose != null &&
    Math.abs(nativeClose - reportingClose) <=
      1e-9 * Math.max(1, Math.abs(nativeClose), Math.abs(reportingClose));
  const useNativeClose =
    nativeClose != null && (reportingClose == null || !closeMatchesReporting);
  const close =
    useNativeClose && nativeClose != null
      ? nativeClose
      : reportingClose ?? nativeClose;
  if (close == null) return null;
  const currency = useNativeClose
    ? normalizedNativeCurrency ?? normalizedReportingCurrency ?? ""
    : normalizedReportingCurrency ?? normalizedNativeCurrency ?? "";
  const date = typeof price.date === "string" ? price.date : null;
  return { close, currency, date };
}

type InstrumentResearchProps = {
  ticker?: string;
};

export default function InstrumentResearch({ ticker }: InstrumentResearchProps) {
  const { ticker: routeTicker } = useParams<{ ticker: string }>();
  const { t } = useTranslation();
  const resolvedTicker =
    typeof ticker === "string" && ticker ? ticker : routeTicker ?? "";
  const hasTickerInput = resolvedTicker.trim().length > 0;
  const tkr =
    resolvedTicker && /^[A-Za-z0-9.-]{1,10}$/.test(resolvedTicker)
      ? resolvedTicker
      : "";
  const tickerParts = tkr.split(".", 2);
  const baseTicker = tickerParts[0] ?? "";
  const initialExchange = tickerParts.length > 1 ? tickerParts[1] ?? "" : "";
  const { tabs, disabledTabs } = useConfig();
  const [overviewHistoryDays, setOverviewHistoryDays] = useState<number>(0);
  // Bumped by "Refresh prices" to remount the Timeseries tab's chart, which
  // fetches its own history outside useInstrumentHistory (#9963).
  const [pricesVersion, setPricesVersion] = useState(0);
  // Overview has no range selector of its own; default to 365d until the
  // Timeseries tab reports a range (0 means "unset"/Max and must still fetch,
  // so resolve it to a positive default here rather than in the hook).
  const overviewFetchDays = overviewHistoryDays > 0 ? overviewHistoryDays : 365;
  const {
    data: detail,
    loading: detailLoading,
    error: detailError,
  } = useInstrumentHistory(tkr, overviewFetchDays);

  // Completes the Plot chores screen's "Research a new stock" chore (#7003)
  // once an actual instrument lookup succeeds here — a no-op unless that
  // navigation set the pending marker.
  useEffect(() => {
    if (tkr && detail) {
      completeTrackedChore("research_new_stock");
    }
  }, [tkr, detail]);

  const [news, setNews] = useState<NewsItem[]>([]);
  const [newsLoading, setNewsLoading] = useState(false);
  const [newsError, setNewsError] = useState<string | null>(null);
  const [instrumentExchange, setInstrumentExchange] = useState(initialExchange);
  const [instrumentIsin, setInstrumentIsin] = useState("");
  const [isinInput, setIsinInput] = useState("");
  // Shown once the backend rejects the ISIN's country prefix for this
  // exchange (422); ticking it resends with allow_foreign_isin (#10005).
  const [foreignIsinRejected, setForeignIsinRejected] = useState(false);
  const [allowForeignIsin, setAllowForeignIsin] = useState(false);
  const [catalogueEntry, setCatalogueEntry] = useState<InstrumentMetadata | null>(null);
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
    | "overview"
    | "timeseries"
    | "positions"
    | "allocation"
    | "fundamentals"
    | "technicals"
    | "news"
    | "notes"
    | "alerts"
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
    setInstrumentIsin("");
    setIsinInput("");
    setForeignIsinRejected(false);
    setAllowForeignIsin(false);
    setCatalogueEntry(null);
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
    const normalizedInstrumentCurrency = normaliseUppercase(detail?.currency ?? undefined);
    const normalizedBaseCurrency =
      detail && typeof detail.base_currency === "string"
        ? normaliseUppercase(detail.base_currency)
        : undefined;
    const currency = normalizedInstrumentCurrency ?? normalizedBaseCurrency;
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
          setInstrumentIsin(normaliseUppercase(matched.isin) ?? "");
          setCatalogueEntry(matched);
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

  const resetIsinEditor = () => {
    setIsinInput(instrumentIsin);
    setForeignIsinRejected(false);
    setAllowForeignIsin(false);
  };

  const handleStartEditing = () => {
    setRefreshPreview(null);
    setRefreshContext(null);
    setRefreshError(null);
    setFormValues(metadata);
    resetIsinEditor();
    setMetadataStatus(null);
    setIsEditingMetadata(true);
  };

  const handleCancelEditing = () => {
    setRefreshPreview(null);
    setRefreshContext(null);
    setRefreshError(null);
    setFormValues(metadata);
    resetIsinEditor();
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
      const refreshedIsin = normaliseUppercase(result.metadata?.isin);
      if (refreshedIsin) setInstrumentIsin(refreshedIsin);
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
      setMetadataStatus({
        kind: "success",
        text:
          result.status === "created"
            ? t("instrumentDetail.metadataCreateSuccess")
            : t("instrumentDetail.refreshSuccess"),
      });
    } catch (err) {
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

  // PUT the metadata; a 404 means the instrument has no metadata file yet
  // (e.g. first research of ZPRX.DE), so create it instead (#10005).
  // Resolves true when the instrument was created.
  const persistMetadata = async (exchange: string, payload: InstrumentMetadata) => {
    const allowForeign = foreignIsinRejected && allowForeignIsin;
    try {
      await updateInstrumentMetadata(baseTicker, exchange, payload, allowForeign);
      return false;
    } catch (err) {
      if (errorStatus(err) !== 404) throw err;
    }
    await createInstrumentMetadata(baseTicker, exchange, payload, allowForeign);
    return true;
  };

  const handleSaveMetadata = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!isEditingMetadata) return;
    const trimmedName = formValues.name.trim();
    const trimmedSector = formValues.sector.trim();
    const trimmedInstrumentType = formValues.instrumentType.trim();
    const selectedCurrency = formValues.currency.trim().toUpperCase();
    const isin = isinInput.trim().toUpperCase();
    if (!selectedCurrency || !SUPPORTED_CURRENCIES.includes(selectedCurrency)) {
      setMetadataStatus({ kind: "error", text: t("instrumentDetail.metadataCurrencyError") });
      return;
    }
    if (isin && !ISIN_PATTERN.test(isin)) {
      setMetadataStatus({ kind: "error", text: t("instrumentDetail.metadataIsinError") });
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
      // Only send the ISIN when it changed, so a catalogue that failed to
      // load (blank instrumentIsin) can't wipe a stored one.
      const isinChanged = isin !== instrumentIsin;
      if (isinChanged) payload.isin = isin || null;
      const created = await persistMetadata(exchange, payload);
      setInstrumentIsin(isin);
      setForeignIsinRejected(false);
      setAllowForeignIsin(false);
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
      setMetadataStatus({
        kind: "success",
        text: created
          ? t("instrumentDetail.metadataCreateSuccess")
          : t("instrumentDetail.metadataSaveSuccess"),
      });
    } catch (err) {
      if (errorStatus(err) === 422 && isin && isin !== instrumentIsin) {
        setForeignIsinRejected(true);
      }
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
        setNews(sortNewsByPublishedAtDesc(items));
      } catch (err) {
        const error = err as { name?: string } | null | undefined;
        if (error?.name === "AbortError") {
          return;
        }
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
        const error = err as { name?: string; status?: number } | null | undefined;
        if (error?.name === "AbortError") return;
        if (!cancelled) {
          if (error?.status === 402) {
            // Genuinely unavailable in this deployment -- never surface the
            // raw backend detail (it names an internal package and a repo
            // URL). Keep the technical detail in the console only (#7221).
            console.error("Unable to load fundamentals (feature unavailable):", err);
            setFundamentalsError(t("instrumentDetail.fundamentalsUnavailable"));
          } else {
            const message = err instanceof Error ? err.message : String(err);
            setFundamentalsError(
              t("instrumentDetail.research.fundamentalsLoadError", { message }),
            );
          }
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
  }, [tkr, activeTab, t]);

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
    ? normaliseUppercase(detail.currency) ??
      (typeof detail.base_currency === "string"
        ? normaliseUppercase(detail.base_currency)
        : undefined)
    : undefined;
  const displayName = metadata.name || detail?.name || null;
  const displaySector = metadata.sector || fallbackSector || "";
  // The instrument's declared/native quote currency -- sourced from the
  // editable metadata catalogue (falling back to the price series only as a
  // best-effort guess before that catalogue has loaded). This is what the
  // "Instrument info" row edits/saves, and it can legitimately disagree
  // with the currency the price is actually being displayed in below (see
  // resolvedCurrentCurrency) -- e.g. a stale catalogue entry (#7219).
  const displayCurrency = metadata.currency || fallbackCurrency || "";
  // The currency the *displayed price* actually agrees with, resolved from
  // the data itself rather than trusted currency-code fields (see
  // resolveDisplayPrice for why detail.currency can't be trusted: routes/
  // instrument.py forces it to the reporting currency whenever a close_gbp
  // column exists, which is nearly always, regardless of what `close` is
  // really quoted in). Everything rendered next to a price -- the header
  // badge, Key Facts, Last Close, the Timeseries tab -- must use this, not
  // displayCurrency, so a GBP-magnitude close never gets mislabelled with a
  // stale metadata currency (#7219).
  const latestRawPriceEntry = (() => {
    const rawPrices = Array.isArray(detail?.prices)
      ? (detail?.prices as unknown[])
      : [];
    const last = rawPrices.length > 0 ? rawPrices[rawPrices.length - 1] : null;
    return last && typeof last === "object" ? (last as Record<string, unknown>) : null;
  })();
  const resolvedLatestPrice = latestRawPriceEntry
    ? resolveDisplayPrice(latestRawPriceEntry, displayCurrency, detail?.base_currency ?? undefined)
    : null;
  const resolvedCurrentCurrency = resolvedLatestPrice?.currency || displayCurrency || "";
  // Compare as currencies, not unit codes: GBX (pence) is the quote unit of
  // GBP, and the price pipeline always normalises GBX closes to pounds
  // (scaling override / close_gbp), so a GBX catalogue entry next to a GBP
  // resolved price is expected, not stale metadata (#9989).
  const metadataCurrencyMismatch = (() => {
    const normalizedMetadata = normaliseUppercase(metadata.currency);
    const normalizedResolved = normaliseUppercase(resolvedCurrentCurrency);
    return (
      normalizedMetadata != null &&
      normalizedResolved != null &&
      normalizeDisplayCurrency(normalizedMetadata) !==
        normalizeDisplayCurrency(normalizedResolved)
    );
  })();
  const fundamentalsCurrency =
    (typeof detail?.base_currency === "string" && detail.base_currency) ||
    resolvedCurrentCurrency ||
    // Unchanged from when the base currency was pinned to GBP (#9753); this
    // page moves to the reporting currency in a later phase of #9766.
    "GBP";
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
  const investingComUrl = buildInvestingComUrl(instrumentIsin, tkr);
  const morningstarId = useMorningstarId(
    baseTicker,
    exchangeForActions,
    instrumentIsin,
    catalogueEntry?.morningstar_id,
  );
  const morningstarUrl = buildMorningstarUrl(instrumentIsin, morningstarId, instrumentType);
  const justEtfUrl = JUSTETF_INSTRUMENT_TYPES.has(instrumentType?.toUpperCase() ?? "")
    ? buildJustEtfUrl(instrumentIsin)
    : null;

  // Price triggers are matched against price-snapshot keys, which are full
  // TICKER.EXCHANGE symbols -- prefer the resolved exchange over whatever
  // suffix (if any) the URL carried so a bare /research/VOD still watches
  // VOD.L. Without an exchange there is no key a trigger could ever match,
  // so leave it empty rather than fall back to the bare ticker (which would
  // hide existing alerts and create ones that never fire). The reference
  // price is the GBP close, since trigger levels are GBP.
  const alertTicker =
    baseTicker && exchangeForActions ? `${baseTicker}.${exchangeForActions}`.toUpperCase() : "";
  const latestGbpClose =
    typeof latestRawPriceEntry?.close_gbp === "number" &&
    Number.isFinite(latestRawPriceEntry.close_gbp)
      ? latestRawPriceEntry.close_gbp
      : null;
  const { count: alertCount, setCount: setAlertCount } = useInstrumentAlertCount(alertTicker);
  const liveTickers = useMemo(() => (tkr ? [tkr] : []), [tkr]);
  const liveQuote = useLiveQuotes(liveTickers)[tkr.toUpperCase()] ?? null;
  const reportingCurrency = normaliseUppercase(detail?.base_currency);
  // Resolved exactly like the last close: `price` is in the units of the
  // history's `close` and `price_gbp` in those of `close_gbp`, so
  // resolveDisplayPrice picks the same figure and currency label for both.
  // A GBP figure is only offered when GBP is the reporting currency, which
  // is what resolveDisplayPrice labels it with.
  const liveDisplayPrice = liveQuote
    ? resolveDisplayPrice(
        (reportingCurrency ?? "GBP") === "GBP"
          ? { close: liveQuote.price, close_gbp: liveQuote.price_gbp }
          : { close: liveQuote.price },
        liveQuote.currency,
        detail?.base_currency ?? undefined,
      )
    : null;
  const formatDisplayPrice = (value: number | null, currency: string) => {
    const normalizedCurrency = normaliseUppercase(currency);
    if (normalizedCurrency && reportingCurrency && normalizedCurrency === reportingCurrency) {
      return money(value, normalizedCurrency);
    }
    return quotedPrice(value, normalizedCurrency ?? currency);
  };
  const liveSummary = (() => {
    if (!liveQuote || !liveDisplayPrice) return null;
    const quoted = new Date(liveQuote.timestamp);
    const day = localDateISO(quoted);
    const clock = quoted.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    const time = day === localDateISO() ? clock : `${day} ${clock}`;
    const change =
      liveQuote.change_pct != null
        ? ` (${liveQuote.change_pct > 0 ? "+" : ""}${percent(liveQuote.change_pct, 2)})`
        : "";
    const parts = [
      `${formatDisplayPrice(liveDisplayPrice.close, liveDisplayPrice.currency)}${change}`,
      t("instrumentDetail.research.label.liveAsOf", { time }),
    ];
    if (liveQuote.is_stale) parts.push(t("instrumentDetail.research.label.liveDelayed"));
    return parts.join(" · ");
  })();
  // Notes don't need a priceable key, so fall back to the URL ticker when the
  // exchange is unknown rather than hiding the tab's content.
  const notesTicker = alertTicker || tkr.toUpperCase();
  const { count: noteCount, setCount: setNoteCount } = useInstrumentNoteCount(notesTicker);
  const tabOptions: { id: typeof activeTab; label: string }[] = [
    { id: "overview", label: t("instrumentDetail.research.tabs.overview") },
    { id: "timeseries", label: t("instrumentDetail.research.tabs.timeseries") },
    { id: "positions", label: t("instrumentDetail.positions") },
    { id: "allocation", label: t("instrumentDetail.research.tabs.allocation") },
    { id: "fundamentals", label: t("instrumentDetail.research.tabs.fundamentals") },
    { id: "technicals", label: t("instrumentDetail.research.tabs.technicals") },
    { id: "news", label: t("instrumentDetail.research.tabs.news") },
    {
      id: "notes",
      label: noteCount
        ? `${t("instrumentNotes.title")} (${noteCount})`
        : t("instrumentNotes.title"),
    },
    {
      id: "alerts",
      label: alertCount
        ? `${t("alertSettings.triggers.instrumentTitle")} (${alertCount})`
        : t("alertSettings.triggers.instrumentTitle"),
    },
  ];
  const standalonePalette = {
    positive: "#137333",
    negative: "#b3261e",
    link: "#1a73e8",
    muted: "#555",
  };

  if (!hasTickerInput) {
    return (
      <EmptyState
        message={t("instrumentDetail.chooseTicker", {
          defaultValue: "Choose a ticker from search to open research.",
        })}
      >
        <div style={{ maxWidth: "28rem", margin: "1rem auto 0" }}>
          <InstrumentSearchBar />
        </div>
      </EmptyState>
    );
  }
  if (!tkr) return <div>{t("instrumentDetail.research.invalidTicker")}</div>;

  return (
    <div style={{ maxWidth: 900, margin: "0 auto", padding: "1rem" }}>
      {(() => {
        const headingName = displayName;
        if (!headingName) {
          return <div style={{ marginBottom: "1rem" }}>{tkr}</div>;
        }
        return (
          <h1 style={{ marginBottom: "1rem" }}>
            {`${tkr} - ${headingName}`}
            {displaySector || resolvedCurrentCurrency ? (
              <span
                style={{
                  display: "block",
                  fontSize: "0.8rem",
                  fontWeight: "normal",
                }}
              >
                {displaySector}
                {displaySector && resolvedCurrentCurrency ? " · " : ""}
                {resolvedCurrentCurrency}
              </span>
            ) : null}
          </h1>
        );
      })()}
      {liveSummary && (
        <div
          data-testid="research-live-price"
          title={liveQuote?.timestamp}
          style={{ marginTop: "-0.5rem", marginBottom: "1rem" }}
        >
          <strong>{t("instrumentDetail.research.label.livePrice")}:</strong> {liveSummary}
        </div>
      )}

      <div style={{ marginBottom: "1rem" }}>
        {tabs.screener && !(disabledTabs ?? []).includes("screener") && (
          <Link to="/screener" style={{ marginRight: "1rem" }}>
            {t("instrumentDetail.research.viewScreener")}
          </Link>
        )}
        {tabs.watchlist && !(disabledTabs ?? []).includes("watchlist") && (
          <Link to="/watchlist">{t("instrumentDetail.research.watchlist")}</Link>
        )}
        <button onClick={toggleWatchlist} style={{ marginLeft: "1rem" }}>
          {inWatchlist
            ? t("instrumentDetail.research.removeFromWatchlist")
            : t("instrumentDetail.research.addToWatchlist")}
        </button>
        <button
          type="button"
          onClick={() => setActiveTab("alerts")}
          style={{ marginLeft: "1rem" }}
        >
          {t("alertSettings.triggers.instrumentTitle")}
        </button>
        {investingComUrl && (
          <a
            href={investingComUrl}
            target="_blank"
            rel="noopener noreferrer"
            style={{ marginLeft: "1rem" }}
          >
            {t("instrumentDetail.research.viewOnInvesting")}
          </a>
        )}
        {morningstarUrl && (
          <a
            href={morningstarUrl}
            target="_blank"
            rel="noopener noreferrer"
            style={{ marginLeft: "1rem" }}
          >
            {t("instrumentDetail.research.viewOnMorningstar")}
          </a>
        )}
        {justEtfUrl && (
          <a
            href={justEtfUrl}
            target="_blank"
            rel="noopener noreferrer"
            style={{ marginLeft: "1rem" }}
          >
            {t("instrumentDetail.research.viewOnJustEtf")}
          </a>
        )}
        {baseTicker && instrumentExchange && (
          <RefreshPricesButton
            ticker={baseTicker}
            exchange={instrumentExchange.toUpperCase()}
            onRefreshed={() => {
              invalidateInstrumentHistory(tkr);
              setPricesVersion((v) => v + 1);
            }}
          />
        )}
        {baseTicker && instrumentExchange && (
          <DeleteSeriesButton ticker={baseTicker} exchange={instrumentExchange.toUpperCase()} />
        )}
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
          <InstrumentIdentifiers
            ticker={alertTicker || tkr}
            exchange={exchangeForActions}
            isin={instrumentIsin}
            morningstarId={morningstarId}
            entry={catalogueEntry}
          />
          {isEditingMetadata && !refreshPreview && (
            <li style={{ marginBottom: "0.5rem" }}>
              <label htmlFor="instrument-isin" style={{ display: "block" }}>
                {t("instrumentDetail.identifiers.isin")}
                <input
                  id="instrument-isin"
                  value={isinInput}
                  onChange={(e) => {
                    setIsinInput(e.target.value);
                    setForeignIsinRejected(false);
                    setAllowForeignIsin(false);
                    setMetadataStatus((prev) => (prev?.kind === "error" ? null : prev));
                  }}
                  maxLength={12}
                  autoComplete="off"
                  spellCheck={false}
                  style={{ display: "block", marginTop: "0.25rem", width: "100%" }}
                  disabled={metadataInputsDisabled}
                />
              </label>
              {foreignIsinRejected && (
                <label
                  htmlFor="instrument-allow-foreign-isin"
                  style={{ display: "flex", gap: "0.4rem", marginTop: "0.25rem" }}
                >
                  <input
                    id="instrument-allow-foreign-isin"
                    type="checkbox"
                    checked={allowForeignIsin}
                    onChange={(e) => setAllowForeignIsin(e.target.checked)}
                    disabled={metadataInputsDisabled}
                  />
                  {t("instrumentDetail.allowForeignIsin")}
                </label>
              )}
            </li>
          )}
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
                {t("instrumentDetail.declaredCurrencyLabel")}
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
                {t("instrumentDetail.declaredCurrencyLabel")}: {displayCurrency || "—"}
              </span>
            )}
            {metadataCurrencyMismatch && (
              <div
                style={{
                  marginTop: "0.25rem",
                  fontSize: "0.8rem",
                  color: "#b3261e",
                }}
              >
                {t("instrumentDetail.currencyMismatchNote", {
                  metadataCurrency: displayCurrency,
                  priceCurrency: resolvedCurrentCurrency,
                })}
              </div>
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
        className="flex-wrap md:flex-nowrap"
        style={{
          display: "flex",
          gap: "0.5rem",
          // At md+ the row is nowrap; with eight tabs it can exceed a
          // tablet-width viewport, so scroll the row rather than the page.
          overflowX: "auto",
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
            const resolvedPrice = resolveDisplayPrice(
              value,
              displayCurrency,
              detail?.base_currency ?? undefined,
            );
            if (!resolvedPrice) return null;
            return resolvedPrice;
          })
          .filter((v): v is DisplayPrice => v != null);

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
        const latestPriceCurrency = latestPriceEntry?.currency ?? resolvedCurrentCurrency;
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

        const percentValue = (ratio: number | null, digits = 2) => {
          if (ratio == null || !Number.isFinite(ratio)) return "—";
          return percent(ratio * 100, digits);
        };

        const summarySections: {
          title: string;
          items: { label: string; value: ReactNode }[];
        }[] = [
          {
            title: t("instrumentDetail.research.section.keyFacts"),
            items: [
              { label: t("common.ticker"), value: tkr },
              { label: t("instrumentDetail.research.label.exchange"), value: instrumentExchange || "—" },
              { label: t("instrumentDetail.sectorLabel"), value: displaySector || "—" },
              { label: t("instrumentDetail.currencyLabel"), value: resolvedCurrentCurrency || "—" },
              ...(liveSummary
                ? [
                    {
                      label: t("instrumentDetail.research.label.livePrice"),
                      value: <span title={liveQuote?.timestamp}>{liveSummary}</span>,
                    },
                  ]
                : []),
              {
                label: t("instrumentDetail.research.label.lastClose"),
                value: latestPrice != null
                  ? formatDisplayPrice(latestPrice, latestPriceCurrency)
                  : "—",
              },
              { label: t("instrumentDetail.research.label.asOf"), value: latestDate ?? "—" },
              { label: t("instrumentDetail.research.label.coverage"), value: formattedCoverage },
              { label: t("instrumentDetail.research.label.dataPoints"), value: rowsCount },
            ],
          },
          {
            title: t("instrumentDetail.research.section.performance"),
            items: [
              { label: t("instrumentDetail.research.label.change7d"), value: percentValue(change7d, 2) },
              { label: t("instrumentDetail.research.label.change30d"), value: percentValue(change30d, 2) },
              {
                label: t("instrumentDetail.research.label.averageDailyReturn30d"),
                value: percentValue(meanReturn, 2),
              },
            ],
          },
          {
            title: t("instrumentDetail.research.section.risk"),
            items: [
              {
                label: t("instrumentDetail.research.label.annualisedVolatility30d"),
                value: percentValue(volatility, 2),
              },
              {
                label: t("dashboard.maxDrawdown"),
                value: percentValue(maxDrawdown != null ? -maxDrawdown : null, 2),
              },
              {
                label: t("instrumentDetail.research.label.worstDay30d"),
                value: percentValue(worstDailyReturn, 2),
              },
            ],
          },
        ];

        return (
          <div style={{ marginBottom: "2rem" }}>
            <h2 style={{ marginBottom: "0.75rem" }}>{t("instrumentDetail.research.summary")}</h2>
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
            key={pricesVersion}
            ticker={tkr}
            name={displayName ?? tkr}
            currency={resolvedCurrentCurrency || undefined}
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

      {activeTab === "positions" && (
        <InstrumentTradeSection
          ticker={tkr}
          positions={positions}
          quoteCurrency={displayCurrency || resolvedCurrentCurrency}
        />
      )}

      {activeTab === "fundamentals" && (
        <div style={{ marginBottom: "2rem" }}>
          <h2 style={{ marginBottom: "0.75rem" }}>{t("instrumentDetail.research.tabs.fundamentals")}</h2>
          <InstrumentValuationPanel ticker={tkr} positions={positions} />
          {fundamentalsLoading ? (
            <div>{t("instrumentDetail.research.loadingFundamentals")}</div>
          ) : fundamentalsError ? (
            <div style={{ color: "red" }}>{fundamentalsError}</div>
          ) : !fundamentals ? (
            <p style={{ margin: 0, color: "#555" }}>
              {t("instrumentDetail.research.fundamentalsNotAvailable")}
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
                  title: t("instrumentDetail.research.section.valuation"),
                  rows: [
                    { label: t("instrumentDetail.research.label.pegRatio"), value: formatRatio(fundamentals.peg_ratio) },
                    { label: t("instrumentDetail.research.label.peRatio"), value: formatRatio(fundamentals.pe_ratio) },
                    {
                      label: t("instrumentDetail.research.label.marketCap"),
                      value: money(fundamentals.market_cap, fundamentalsCurrency),
                    },
                    {
                      label: t("instrumentDetail.research.label.freeCashFlow"),
                      value: money(fundamentals.fcf, fundamentalsCurrency),
                    },
                    {
                      label: t("instrumentDetail.research.label.earningsPerShare"),
                      value: formatRatio(fundamentals.eps),
                    },
                  ],
                },
                {
                  title: t("instrumentDetail.research.section.financialHealth"),
                  rows: [
                    { label: t("instrumentDetail.research.label.debtEquity"), value: formatRatio(fundamentals.de_ratio) },
                    {
                      label: t("instrumentDetail.research.label.longTermDebtEquity"),
                      value: formatRatio(fundamentals.lt_de_ratio),
                    },
                    {
                      label: t("instrumentDetail.research.label.interestCoverage"),
                      value: formatRatio(fundamentals.interest_coverage),
                    },
                    {
                      label: t("instrumentDetail.research.label.currentRatio"),
                      value: formatRatio(fundamentals.current_ratio),
                    },
                    {
                      label: t("instrumentDetail.research.label.quickRatio"),
                      value: formatRatio(fundamentals.quick_ratio),
                    },
                  ],
                },
                {
                  title: t("instrumentDetail.research.section.profitability"),
                  rows: [
                    {
                      label: t("instrumentDetail.research.label.grossMargin"),
                      value: formatPercent(fundamentals.gross_margin),
                    },
                    {
                      label: t("instrumentDetail.research.label.operatingMargin"),
                      value: formatPercent(fundamentals.operating_margin),
                    },
                    {
                      label: t("instrumentDetail.research.label.netMargin"),
                      value: formatPercent(fundamentals.net_margin),
                    },
                    {
                      label: t("instrumentDetail.research.label.ebitdaMargin"),
                      value: formatPercent(fundamentals.ebitda_margin),
                    },
                    { label: t("instrumentDetail.research.label.roa"), value: formatPercent(fundamentals.roa) },
                    { label: t("instrumentDetail.research.label.roe"), value: formatPercent(fundamentals.roe) },
                    { label: t("instrumentDetail.research.label.roi"), value: formatPercent(fundamentals.roi) },
                  ],
                },
                {
                  title: t("instrumentDetail.research.section.shareholderMetrics"),
                  rows: [
                    {
                      label: t("instrumentDetail.research.label.dividendYield"),
                      value: formatPercent(fundamentals.dividend_yield),
                    },
                    {
                      label: t("instrumentDetail.research.label.dividendPayoutRatio"),
                      value: formatPercent(fundamentals.dividend_payout_ratio),
                    },
                    { label: t("instrumentDetail.research.label.beta"), value: formatRatio(fundamentals.beta) },
                    {
                      label: t("instrumentDetail.research.label.sharesOutstanding"),
                      value: formatInteger(fundamentals.shares_outstanding),
                    },
                    {
                      label: t("instrumentDetail.research.label.floatShares"),
                      value: formatInteger(fundamentals.float_shares),
                    },
                    {
                      label: t("instrumentDetail.research.label.high52w"),
                      value: money(fundamentals.high_52w, fundamentalsCurrency),
                    },
                    {
                      label: t("instrumentDetail.research.label.low52w"),
                      value: money(fundamentals.low_52w, fundamentalsCurrency),
                    },
                    {
                      label: t("instrumentDetail.research.label.averageVolume"),
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
                        aria-label={t("instrumentDetail.research.fundamentalsTableAria", {
                          section: section.title,
                        })}
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

      {activeTab === "allocation" && (
        <div style={{ marginBottom: "2rem" }}>
          <h2 style={{ marginBottom: "0.75rem" }}>{t("instrumentDetail.research.tabs.allocation")}</h2>
          <InstrumentAllocationPanel ticker={tkr} />
        </div>
      )}

      {activeTab === "technicals" && (
        <div style={{ marginBottom: "2rem" }}>
          <h2 style={{ marginBottom: "0.75rem" }}>{t("instrumentDetail.research.tabs.technicals")}</h2>
          <InstrumentTechnicalsPanel ticker={tkr} />
        </div>
      )}

      {activeTab === "news" && (
        <>
          {newsLoading ? (
            <div>{t("instrumentDetail.research.loadingNews")}</div>
          ) : newsError ? (
            <div>{newsError}</div>
          ) : news.length === 0 ? (
            <EmptyState message={t("instrumentDetail.research.noNews")} />
          ) : (
            <div>
              <h2>{t("instrumentDetail.research.tabs.news")}</h2>
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

      {activeTab === "notes" && (
        <InstrumentNotesSection
          ticker={notesTicker}
          latestPrice={latestGbpClose}
          onCountChange={setNoteCount}
        />
      )}

      {activeTab === "alerts" && (
        <InstrumentAlertsSection
          ticker={alertTicker}
          latestPrice={latestGbpClose}
          onCountChange={setAlertCount}
        />
      )}
    </div>
  );
}
