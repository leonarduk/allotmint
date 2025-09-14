import { useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";
        
import { FixedSizeGrid as Grid } from "react-window";
import { getOwners, getPortfolio } from "../api";
import type { InstrumentSummary, OwnerSummary, Portfolio } from "../types";
import InstrumentTile from "../components/InstrumentTile";
import SummaryBar from "../components/SummaryBar";
import { PortfolioView } from "../components/PortfolioView";
import { useRoute } from "../RouteContext";
import useFetchWithRetry from "../hooks/useFetchWithRetry";

export function Member() {
  const { owner } = useParams<{ owner?: string }>();
  const [data, setData] = useState<Portfolio | null>(null);

  const { selectedOwner, setSelectedOwner } = useRoute();
  const [retryNonce, setRetryNonce] = useState(0);

  const ownersReq = useFetchWithRetry<OwnerSummary[]>(getOwners, 500, 5, [retryNonce]);

  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);

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
    if (!selectedOwner) {
      setPortfolio(null);
      return;
    }
    setLoading(true);
    setError(null);
    getPortfolio(selectedOwner)
      .then((p) => {
        setPortfolio(p);
        setError(null);
      })
      .catch(() => setError("Failed to load portfolio"))
      .finally(() => setLoading(false));
  }, [selectedOwner, retryNonce]);

  return (
    <div className="p-4 md:p-8">
      <SummaryBar
        owners={ownersReq.data ?? []}
        owner={selectedOwner}
        onOwnerChange={setSelectedOwner}
        onRefresh={() => setRetryNonce((n) => n + 1)}
      />
      <PortfolioView data={portfolio} loading={loading} error={error} />
    </div>
  );
}

export default Member;
