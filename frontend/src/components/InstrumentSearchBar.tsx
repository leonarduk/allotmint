import { useEffect, useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { searchInstruments } from "../api";

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

export function InstrumentSearchBar() {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [sector, setSector] = useState("");
  const [region, setRegion] = useState("");
  const [results, setResults] = useState<Result[]>([]);
  const [index, setIndex] = useState(-1);
  const listRef = useRef<HTMLUListElement | null>(null);

  useEffect(() => {
    let ignore = false;
    if (query.length < 2) {
      setResults([]);
      return;
    }
    searchInstruments(query, sector || undefined, region || undefined)
      .then((r) => {
        if (!ignore) setResults(r);
      })
      .catch(() => {
        if (!ignore) setResults([]);
      });
    return () => {
      ignore = true;
    };
  }, [query, sector, region]);

  const navigateTo = (tkr: string) => {
    setQuery("");
    setResults([]);
    navigate(`/research/${encodeURIComponent(tkr)}`);
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
    <div style={{ position: "relative", marginLeft: "1rem" }}>
      <div style={{ display: "flex", gap: "0.25rem" }}>
        <input
          type="text"
          placeholder="Search…"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setIndex(-1);
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
}
