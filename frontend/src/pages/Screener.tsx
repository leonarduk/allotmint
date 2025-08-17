import { useState } from "react";
import { useTranslation } from "react-i18next";
import { getScreener } from "../api";
import type { ScreenerResult } from "../types";
import { useSortableTable } from "../hooks/useSortableTable";
import { InstrumentDetail } from "../components/InstrumentDetail";
import i18n from "../i18n";

export function Screener() {
  const [tickers, setTickers] = useState("");
  const [pegMax, setPegMax] = useState("");
  const [peMax, setPeMax] = useState("");
  const [deMax, setDeMax] = useState("");
  const [fcfMin, setFcfMin] = useState("");
  const [pbMax, setPbMax] = useState("");
  const [psMax, setPsMax] = useState("");
  const [pcMax, setPcMax] = useState("");
  const [pfcfMax, setPfcfMax] = useState("");
  const [pEbitdaMax, setPEbitdaMax] = useState("");
  const [evEbitdaMax, setEvEbitdaMax] = useState("");
  const [evRevenueMax, setEvRevenueMax] = useState("");

  const [rows, setRows] = useState<ScreenerResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const { t } = useTranslation();

  const { sorted, handleSort } = useSortableTable(rows, "peg_ratio");

  const cell = { padding: "4px 6px" } as const;
  const right = { ...cell, textAlign: "right", cursor: "pointer" } as const;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const symbols = tickers
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean);
    if (!symbols.length) return;

    setLoading(true);
    setError(null);
    try {
      const data = await getScreener(symbols, {
        peg_max: pegMax ? parseFloat(pegMax) : undefined,
        pe_max: peMax ? parseFloat(peMax) : undefined,
        de_max: deMax ? parseFloat(deMax) : undefined,
        fcf_min: fcfMin ? parseFloat(fcfMin) : undefined,
        pb_max: pbMax ? parseFloat(pbMax) : undefined,
        ps_max: psMax ? parseFloat(psMax) : undefined,
        pc_max: pcMax ? parseFloat(pcMax) : undefined,
        pfcf_max: pfcfMax ? parseFloat(pfcfMax) : undefined,
        pebitda_max: pEbitdaMax ? parseFloat(pEbitdaMax) : undefined,
        ev_ebitda_max: evEbitdaMax ? parseFloat(evEbitdaMax) : undefined,
        ev_revenue_max: evRevenueMax ? parseFloat(evRevenueMax) : undefined,
      });
      setRows(data);
    } catch (e) {
      setRows([]);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <form onSubmit={handleSubmit} style={{ marginBottom: "1rem" }}>
        <label style={{ marginRight: "0.5rem" }}>
          {t("screener.tickers")}
          <input
            aria-label={t("screener.tickers")}
            type="text"
            value={tickers}
            onChange={(e) => setTickers(e.target.value)}
            placeholder="AAPL,MSFT,…"
            style={{ marginLeft: "0.25rem" }}
          />
        </label>
        <label style={{ marginRight: "0.5rem" }}>
          {t("screener.maxPeg")}
          <input
            aria-label={t("screener.maxPeg")}
            type="number"
            value={pegMax}
            onChange={(e) => setPegMax(e.target.value)}
            step="any"
            style={{ marginLeft: "0.25rem" }}
          />
        </label>
        <label style={{ marginRight: "0.5rem" }}>
          {t("screener.maxPe")}
          <input
            aria-label={t("screener.maxPe")}
            type="number"
            value={peMax}
            onChange={(e) => setPeMax(e.target.value)}
            step="any"
            style={{ marginLeft: "0.25rem" }}
          />
        </label>
        <label style={{ marginRight: "0.5rem" }}>
          {t("screener.maxDe")}
          <input
            aria-label={t("screener.maxDe")}
            type="number"
            value={deMax}
            onChange={(e) => setDeMax(e.target.value)}
            step="any"
            style={{ marginLeft: "0.25rem" }}
          />
        </label>
        <label style={{ marginRight: "0.5rem" }}>
          {t("screener.minFcf")}
          <input
            aria-label={t("screener.minFcf")}
            type="number"
            value={fcfMin}
            onChange={(e) => setFcfMin(e.target.value)}
            step="any"
            style={{ marginLeft: "0.25rem" }}
          />
        </label>
        <label style={{ marginRight: "0.5rem" }}>
          {t("screener.maxPb")}
          <input
            aria-label={t("screener.maxPb")}
            type="number"
            value={pbMax}
            onChange={(e) => setPbMax(e.target.value)}
            step="any"
            style={{ marginLeft: "0.25rem" }}
          />
        </label>
        <label style={{ marginRight: "0.5rem" }}>
          {t("screener.maxPs")}
          <input
            aria-label={t("screener.maxPs")}
            type="number"
            value={psMax}
            onChange={(e) => setPsMax(e.target.value)}
            step="any"
            style={{ marginLeft: "0.25rem" }}
          />
        </label>
        <label style={{ marginRight: "0.5rem" }}>
          {t("screener.maxPc")}
          <input
            aria-label={t("screener.maxPc")}
            type="number"
            value={pcMax}
            onChange={(e) => setPcMax(e.target.value)}
            step="any"
            style={{ marginLeft: "0.25rem" }}
          />
        </label>
        <label style={{ marginRight: "0.5rem" }}>
          {t("screener.maxPfcf")}
          <input
            aria-label={t("screener.maxPfcf")}
            type="number"
            value={pfcfMax}
            onChange={(e) => setPfcfMax(e.target.value)}
            step="any"
            style={{ marginLeft: "0.25rem" }}
          />
        </label>
        <label style={{ marginRight: "0.5rem" }}>
          {t("screener.maxPebitda")}
          <input
            aria-label={t("screener.maxPebitda")}
            type="number"
            value={pEbitdaMax}
            onChange={(e) => setPEbitdaMax(e.target.value)}
            step="any"
            style={{ marginLeft: "0.25rem" }}
          />
        </label>
        <label style={{ marginRight: "0.5rem" }}>
          {t("screener.maxEvEbitda")}
          <input
            aria-label={t("screener.maxEvEbitda")}
            type="number"
            value={evEbitdaMax}
            onChange={(e) => setEvEbitdaMax(e.target.value)}
            step="any"
            style={{ marginLeft: "0.25rem" }}
          />
        </label>
        <label style={{ marginRight: "0.5rem" }}>
          {t("screener.maxEvRevenue")}
          <input
            aria-label={t("screener.maxEvRevenue")}
            type="number"
            value={evRevenueMax}
            onChange={(e) => setEvRevenueMax(e.target.value)}
            step="any"
            style={{ marginLeft: "0.25rem" }}
          />
        </label>
        <button type="submit" disabled={loading} style={{ marginLeft: "0.5rem" }}>
          {loading ? t("screener.loading") : t("screener.run")}
        </button>
      </form>

      {error && <p style={{ color: "red" }}>{error}</p>}
      {loading && <p>{t("screener.loading")}</p>}

      {rows.length > 0 && !loading && (
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <th
                style={{ ...cell, cursor: "pointer" }}
                onClick={() => handleSort("ticker")}
              >
                Ticker
              </th>
              <th style={right} onClick={() => handleSort("peg_ratio")}>PEG</th>
              <th style={right} onClick={() => handleSort("pe_ratio")}>P/E</th>
              <th style={right} onClick={() => handleSort("de_ratio")}>D/E</th>
              <th style={right} onClick={() => handleSort("fcf")}>FCF</th>
              <th style={right} onClick={() => handleSort("pb_ratio")}>P/B</th>
              <th style={right} onClick={() => handleSort("ps_ratio")}>P/S</th>
              <th style={right} onClick={() => handleSort("pc_ratio")}>P/C</th>
              <th style={right} onClick={() => handleSort("pfcf_ratio")}>P/FCF</th>
              <th style={right} onClick={() => handleSort("p_ebitda")}>P/EBITDA</th>
              <th style={right} onClick={() => handleSort("ev_to_ebitda")}>EV/EBITDA</th>
              <th style={right} onClick={() => handleSort("ev_to_revenue")}>EV/Revenue</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((r) => (
              <tr
                key={r.ticker}
                onClick={() => setSelected(r.ticker)}
                style={{ cursor: "pointer" }}
              >
                <td style={cell}>{r.ticker}</td>
                <td style={right}>{r.peg_ratio ?? "—"}</td>
                <td style={right}>{r.pe_ratio ?? "—"}</td>
                <td style={right}>{r.de_ratio ?? "—"}</td>
                <td style={right}>
                  {r.fcf != null
                    ? new Intl.NumberFormat(i18n.language).format(r.fcf)
                    : "—"}
                </td>
                <td style={right}>{r.pb_ratio ?? "—"}</td>
                <td style={right}>{r.ps_ratio ?? "—"}</td>
                <td style={right}>{r.pc_ratio ?? "—"}</td>
                <td style={right}>{r.pfcf_ratio ?? "—"}</td>
                <td style={right}>{r.p_ebitda ?? "—"}</td>
                <td style={right}>{r.ev_to_ebitda ?? "—"}</td>
                <td style={right}>{r.ev_to_revenue ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {selected && (
        <InstrumentDetail
          ticker={selected}
          name={rows.find((r) => r.ticker === selected)?.name ?? ""}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  );
}

export default Screener;

