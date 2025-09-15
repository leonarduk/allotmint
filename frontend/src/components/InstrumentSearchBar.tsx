import { useEffect, useState, useRef, memo, useId } from "react";
import { useNavigate } from "react-router-dom";
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
  onNavigate?: () => void;
}

const InstrumentSearchBar = memo(function InstrumentSearchBar({
  onNavigate,
}: InstrumentSearchBarProps) {
  const navigate = useNavigate();
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
            setError("Search failed");
          }
        });
    }, 300);
    return () => {
      controller.abort();
      clearTimeout(timeout);
    };
  }, [query, sector, region]);

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
    <div
      style={{
        position: "relative",
        flex: 1,
        minWidth: "15rem",
      }}
    >
      <div style={{ display: "flex", gap: "0.25rem" }}>
        <input
          type="text"
          placeholder="Search…"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setIndex(-1);
            setError(null);
          }}
          onKeyDown={handleKeyDown}
          style={{ padding: "0.25rem" }}
          aria-label="Search instruments"
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
              key={r.ticker}
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
});

export function InstrumentSearchBarToggle() {
  const [open, setOpen] = useState(false);
  const contentId = useId();

  return (
    <Collapsible open={open} onOpenChange={setOpen} style={{ marginLeft: "1rem" }}>
      <CollapsibleTrigger
        type="button"
        aria-controls={contentId}
        aria-expanded={open}
        style={{
          padding: "0.25rem 0.75rem",
          borderRadius: "0.25rem",
          border: "1px solid #ccc",
          background: open ? "#eee" : "#fff",
          cursor: "pointer",
        }}
      >
        Research
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
          <button
            type="button"
            onClick={() => setOpen(false)}
            aria-label="Close search"
            style={{
              padding: "0.25rem 0.5rem",
              borderRadius: "0.25rem",
              border: "1px solid #ccc",
              background: "#f5f5f5",
              cursor: "pointer",
              alignSelf: "center",
            }}
          >
            Close
          </button>
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}

export default InstrumentSearchBarToggle;

export { InstrumentSearchBar };
