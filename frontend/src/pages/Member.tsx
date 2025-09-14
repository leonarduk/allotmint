import { useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { FixedSizeGrid as Grid } from "react-window";
import { getPortfolio } from "../api";
import type { InstrumentSummary, Portfolio } from "../types";
import InstrumentTile from "../components/InstrumentTile";

export function Member() {
  const { owner } = useParams<{ owner?: string }>();
  const [data, setData] = useState<Portfolio | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!owner) return;
    setLoading(true);
    getPortfolio(owner)
      .then((p) => {
        setData(p);
        setError(null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, [owner]);

  const instruments: InstrumentSummary[] = useMemo(() => {
    if (!data) return [];
    return data.accounts.flatMap((a) =>
      a.holdings.map((h) => ({
        ticker: h.ticker,
        name: h.name,
        currency: h.currency,
        units: h.units,
        market_value_gbp: h.market_value_gbp ?? 0,
        market_value_currency: h.market_value_currency,
        gain_gbp: h.gain_gbp ?? 0,
        gain_currency: h.gain_currency,
        instrument_type: h.instrument_type,
        gain_pct: h.gain_pct,
        last_price_gbp: h.current_price_gbp ?? undefined,
        last_price_currency: h.current_price_currency ?? undefined,
        last_price_date: h.last_price_date ?? undefined,
        change_7d_pct: undefined,
        change_30d_pct: undefined,
      })),
    );
  }, [data]);

  const containerRef = useRef<HTMLDivElement>(null);
  const [dimensions, setDimensions] = useState({ width: 0, height: 0 });

  useEffect(() => {
    const el = containerRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver((entries) => {
      const { width, height } = entries[0].contentRect;
      setDimensions({ width, height });
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const tileW = 250;
  const tileH = 160;
  const columnCount = Math.max(1, Math.floor(dimensions.width / tileW));
  const rowCount = Math.ceil(instruments.length / columnCount);

  if (!owner) return <div>Select a member.</div>;
  if (loading) return <div>Loading…</div>;
  if (error) return <div>{error}</div>;

  if (instruments.length > 200) {
    return (
      <div
        ref={containerRef}
        style={{ width: "100%", height: "80vh" }}
      >
        <Grid
          columnCount={columnCount}
          columnWidth={tileW}
          height={dimensions.height || 600}
          rowCount={rowCount}
          rowHeight={tileH}
          width={dimensions.width || 1}
        >
          {({ columnIndex, rowIndex, style }) => {
            const idx = rowIndex * columnCount + columnIndex;
            const inst = instruments[idx];
            if (!inst) return null;
            return (
              <div style={style}>
                <InstrumentTile instrument={inst} />
              </div>
            );
          }}
        </Grid>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      style={{
        display: "grid",
        gap: "1rem",
        gridTemplateColumns: "repeat(auto-fill, minmax(250px, 1fr))",
      }}
    >
      {instruments.map((inst) => (
        <InstrumentTile key={inst.ticker} instrument={inst} />
      ))}
    </div>
  );
}

export default Member;
