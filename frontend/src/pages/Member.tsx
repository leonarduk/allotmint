import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useNavigate, useParams } from "react-router-dom";

import { FixedSizeGrid as Grid } from "react-window";
import { getOwners, getPortfolio } from "../api";
import type { InstrumentSummary, OwnerSummary, Portfolio } from "../types";
import InstrumentTile from "../components/InstrumentTile";
import { InstrumentTable } from "../components/InstrumentTable";
import SummaryBar from "../components/SummaryBar";
import { PortfolioView } from "../components/PortfolioView";
import { useRoute } from "../RouteContext";
import useFetchWithRetry from "../hooks/useFetchWithRetry";

export function Member() {
  const { owner: ownerParam } = useParams<{ owner?: string }>();
  const navigate = useNavigate();
  const { selectedOwner, setSelectedOwner } = useRoute();
  const [retryNonce, setRetryNonce] = useState(0);
  const [viewMode, setViewMode] = useState<"table" | "tiles">("table");

  const ownersReq = useFetchWithRetry<OwnerSummary[]>(getOwners, 500, 5, [retryNonce]);

  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const normalizedOwner = ownerParam ?? "";
    if (selectedOwner !== normalizedOwner) {
      setSelectedOwner(normalizedOwner);
    }
  }, [ownerParam, selectedOwner, setSelectedOwner]);

  const owner = ownerParam ?? selectedOwner;

  const handleOwnerChange = useCallback(
    (newOwner: string) => {
      if (newOwner === owner) return;
      setSelectedOwner(newOwner);
      navigate(newOwner ? `/member/${newOwner}` : "/member");
    },
    [navigate, owner, setSelectedOwner],
  );

  const handleRefresh = useCallback(() => {
    setRetryNonce((n) => n + 1);
  }, []);

  useEffect(() => {
    if (!owner) {
      setPortfolio(null);
      setLoading(false);
      setError(null);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);

    getPortfolio(owner)
      .then((p) => {
        if (cancelled) return;
        setPortfolio(p);
        setError(null);
      })
      .catch((err) => {
        if (cancelled) return;
        const message =
          err instanceof Error
            ? err.message
            : typeof err === "string"
              ? err
              : "Failed to load portfolio";
        setError(message);
        setPortfolio(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [owner, retryNonce]);

  const instruments: InstrumentSummary[] = useMemo(() => {
    if (!portfolio) return [];
    return portfolio.accounts.flatMap((account) =>
      account.holdings.map((holding) => ({
        ticker: holding.ticker,
        name: holding.name,
        currency: holding.currency ?? undefined,
        units: holding.units,
        market_value_gbp: holding.market_value_gbp ?? 0,
        market_value_currency: holding.market_value_currency ?? undefined,
        gain_gbp: holding.gain_gbp ?? 0,
        gain_currency: holding.gain_currency ?? undefined,
        instrument_type: holding.instrument_type ?? undefined,
        gain_pct: holding.gain_pct,
        last_price_gbp: holding.current_price_gbp ?? undefined,
        last_price_currency: holding.current_price_currency ?? undefined,
        last_price_date: holding.last_price_date ?? undefined,
        change_7d_pct: undefined,
        change_30d_pct: undefined,
      })),
    );
  }, [portfolio]);

  const containerRef = useRef<HTMLDivElement>(null);
  const [dimensions, setDimensions] = useState({ width: 0, height: 0 });

  const hasRenderableHoldings = Boolean(
    !loading && !error && portfolio && instruments.length > 0,
  );
  const isTileView = viewMode === "tiles";

  useEffect(() => {
    if (!hasRenderableHoldings || !isTileView) {
      setDimensions({ width: 0, height: 0 });
      return;
    }

    const el = containerRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;

    const observer = new ResizeObserver((entries) => {
      const { width, height } = entries[0].contentRect;
      setDimensions({ width, height });
    });

    observer.observe(el);
    return () => observer.disconnect();
  }, [hasRenderableHoldings, isTileView]);

  const tileW = 250;
  const tileH = 160;

  const renderInstruments = (): ReactNode => {
    if (!owner) {
      return <div>Select a member.</div>;
    }

    if (loading) {
      return <div>Loading instruments…</div>;
    }

    if (error) {
      return <div className="text-error">{error}</div>;
    }

    if (!portfolio || instruments.length === 0) {
      return <div>No holdings found.</div>;
    }

    if (!isTileView) {
      return <InstrumentTable rows={instruments} />;
    }

    if (instruments.length > 200) {
      const columnCount = Math.max(
        1,
        Math.floor((dimensions.width || tileW) / tileW),
      );
      const rowCount = Math.ceil(instruments.length / columnCount);

      return (
        <div ref={containerRef} style={{ width: "100%", height: "80vh" }}>
          <Grid
            columnCount={columnCount}
            columnWidth={tileW}
            height={dimensions.height || 600}
            rowCount={rowCount}
            rowHeight={tileH}
            width={dimensions.width || tileW}
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
  };

  return (
    <div className="space-y-4 p-4 md:p-8">
      <SummaryBar
        owners={ownersReq.data ?? []}
        owner={owner}
        onOwnerChange={handleOwnerChange}
        onRefresh={handleRefresh}
      />
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr),minmax(0,1fr)]">
        <PortfolioView data={portfolio} loading={loading} error={error} />
        <div className="min-h-[200px] space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-lg font-semibold">Holdings</h2>
            <label className="flex items-center gap-2 text-sm">
              View:
              <select
                value={viewMode}
                onChange={(event) =>
                  setViewMode(event.target.value as "table" | "tiles")
                }
                className="rounded border px-2 py-1"
              >
                <option value="table">Table</option>
                <option value="tiles">Tiles</option>
              </select>
            </label>
          </div>
          {renderInstruments()}
        </div>
      </div>
    </div>
  );
}

export default Member;
