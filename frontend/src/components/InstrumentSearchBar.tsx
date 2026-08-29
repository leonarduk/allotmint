import { useEffect, useState, useRef, memo, useId } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Lightbulb } from "lucide-react";
import { searchInstruments } from "../api";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "./ui/collapsible";

interface Result {
  ticker: string;
  name: string;
  sector?: string;
  region?: string;
}

const SECTORS = [
  "Energy",
  "Materials",
  "Industrials",
  "Consumer Discretionary",
  "Consumer Staples",
  "Health Care",
  "Financials",
  "Information Technology",
  "Communication Services",
  "Utilities",
  "Real Estate",
];

const REGIONS = ["Africa", "Asia", "Europe", "North America", "South America", "Oceania", "UK", "US"];

interface InstrumentSearchBarProps {
  id?: string;
  onClose?: () => void;
  onNavigate?: () => void;
}

function InstrumentSearchBarComponent({
  id,
  onClose,
  onNavigate,
}: InstrumentSearchBarProps) {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [query, setQuery] = useState("");
  const [sector, setSector] = useState("");
  const [region, setRegion] = useState("");
  const [results, setResults] = useState<Result[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [index, setIndex] = useState(-1);
  const listRef = useRef<HTMLUListElement | null>(null);

  useEffect(() => {
    const trimmed = query.trim();
    if (trimmed.length < 2) {
      setResults([]);
      setError(null);
      return;
    }
    const controller = new AbortController();
    const timeout = setTimeout(() => {
      searchInstruments(
        trimmed,
        sector || undefined,
        region || undefined,
        controller.signal,
      )
        .then((res) => {
          setResults(res);
          setError(null);
        })
        .catch((err) => {
          if (err.name !== "AbortError") {
            console.error(err);
            setResults([]);
            setError(t("instrumentDetail.searchFailed"));
          }
        });
    }, 300);
    return () => {
      controller.abort();
      clearTimeout(timeout);
    };
  }, [query, sector, region, t]);

  const navigateTo = (tkr: string) => {
    setQuery("");
    setResults([]);
    navigate(`/research/${encodeURIComponent(tkr)}`);
    onNavigate?.();
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setIndex((i) => Math.min(i + 1, results.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      const sel = results[index] || results[0];
      if (sel) navigateTo(sel.ticker);
    }
  };

  return (
    <div id={id} style={{ position: "relative" }}>
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "0.25rem",
          alignItems: "center",
        }}
      >

        <input
          type="text"
          placeholder={t("instrumentDetail.searchPlaceholder")}
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setIndex(-1);
            setError(null);
          }}
          onKeyDown={handleKeyDown}
          style={{ padding: "0.25rem" }}
          aria-label={t("instrumentDetail.searchInputLabel")}
        />
        <select
          value={sector}
          onChange={(e) => setSector(e.target.value)}
          aria-label="Filter by sector"
        >
          <option value="">All sectors</option>
          {SECTORS.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <select
          value={region}
          onChange={(e) => setRegion(e.target.value)}
          aria-label="Filter by region"
        >
          <option value="">All regions</option>
          {REGIONS.map((r) => (
            <option key={r} value={r}>
              {r}
            </option>
          ))}
        </select>
        {onClose && (
          <button
            type="button"
            aria-label="Close search"
            onClick={onClose}
            style={{
              border: "1px solid #ccc",
              background: "#fff",
              borderRadius: "9999px",
              width: "1.5rem",
              height: "1.5rem",
              lineHeight: 1,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "#213547",
              cursor: "pointer",
              padding: 0,
            }}
          >
            ×
          </button>
        )}
      </div>
      {error && (
        <div role="alert" style={{ color: "red" }}>
          {error}
        </div>
      )}
      {results.length > 0 && (
        <ul
          ref={listRef}
          style={{
            listStyle: "none",
            margin: 0,
            padding: 0,
            position: "absolute",
            background: "#fff",
            color: "#000",
            zIndex: 1000,
            width: "100%",
            maxHeight: "15rem",
            overflowY: "auto",
            border: "1px solid #ccc",
          }}
        >
          {results.map((r, i) => (
            <li
              key={`${r.ticker}-${i}`}
              style={{
                padding: "0.25rem 0.5rem",
                background: i === index ? "#eee" : undefined,
                cursor: "pointer",
              }}
              onMouseDown={() => navigateTo(r.ticker)}
            >
              {r.ticker} — {r.name}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

const InstrumentSearchBar = memo(InstrumentSearchBarComponent);

export function InstrumentSearchBarToggle() {
  const [open, setOpen] = useState(false);
  const contentId = useId();
  const { t } = useTranslation();
  // #7205: this was previously labelled with the "Research" menu-entry
  // string (app.research), which reads as a page name, not a search
  // control — a screen reader user had no way to tell this icon opens a
  // search box. Use a dedicated, search-specific label instead.
  // It also needs to be distinct from the "Search instruments" label on the
  // input this toggle reveals — with the panel open, a screen reader would
  // otherwise meet a button and two inputs all sharing one accessible name
  // (#7223).
  const searchLabel = t("instrumentDetail.searchToggleLabel");

  return (
    <Collapsible open={open} onOpenChange={setOpen} style={{ marginLeft: "1rem" }}>
      <CollapsibleTrigger
        type="button"
        aria-controls={contentId}
        aria-expanded={open}
        aria-label={searchLabel}
        style={{
          padding: "0.25rem",
          borderRadius: "0.25rem",
          border: "1px solid #ccc",
          background: open ? "#eee" : "#fff",
          color: "#213547",
          cursor: "pointer",
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <Lightbulb aria-hidden="true" size={18} />
      </CollapsibleTrigger>
      <CollapsibleContent
        id={contentId}
        style={{
          marginTop: "0.5rem",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "flex-start",
            gap: "0.5rem",
          }}
        >
          <InstrumentSearchBar onNavigate={() => setOpen(false)} />
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}

export { InstrumentSearchBar };

export default InstrumentSearchBarToggle;
