import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { getOwners, getTransactionsWithCompliance, requestApproval } from "../api";
import type { OwnerSummary, TransactionWithCompliance } from "../types";
import { OwnerSelector } from "../components/OwnerSelector";

export default function TradeCompliance() {
  const { owner: ownerParam } = useParams<{ owner?: string }>();
  const navigate = useNavigate();
  const [owners, setOwners] = useState<OwnerSummary[]>([]);
  const [owner, setOwner] = useState(ownerParam ?? "");
  const [trades, setTrades] = useState<TransactionWithCompliance[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [requested, setRequested] = useState<Record<string, boolean>>({});

  useEffect(() => {
    getOwners().then(setOwners).catch(() => setOwners([]));
  }, []);

  useEffect(() => {
    if (!owner) {
      setTrades([]);
      return;
    }
    getTransactionsWithCompliance(owner)
      .then((res) => {
        setTrades(res.transactions);
        setError(null);
      })
      .catch((e) => {
        setError(e instanceof Error ? e.message : String(e));
        setTrades([]);
      });
  }, [owner]);

  const handleRequest = (ticker: string) => {
    requestApproval(owner, ticker)
      .then(() => {
        setRequested((r) => ({ ...r, [ticker]: true }));
      })
      .catch((e) => console.error("request approval failed", e));
  };

  return (
    <div style={{ maxWidth: 900, margin: "0 auto", padding: "1rem" }}>
      <h1>Trade compliance</h1>
      <OwnerSelector
        owners={owners}
        selected={owner}
        onSelect={(o) => {
          setOwner(o);
          navigate(`/trade-compliance/${o}`);
        }}
      />
      {error && <p style={{ color: "red" }}>{error}</p>}
      {owner && trades.length > 0 && (
        <table style={{ width: "100%", marginTop: "1rem" }}>
          <thead>
            <tr>
              <th>Date</th>
              <th>Ticker</th>
              <th>Type</th>
              <th>Warnings</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {trades.map((t, idx) => (
              <tr key={idx}>
                <td>{t.date}</td>
                <td>{t.ticker}</td>
                <td>{t.type || t.kind}</td>
                <td>{t.warnings.join("; ")}</td>
                <td>
                  {t.warnings.some((w) => w.includes("without approval")) &&
                    t.ticker && (
                      <button
                        onClick={() => handleRequest(t.ticker!)}
                        disabled={requested[t.ticker!]}
                      >
                        {requested[t.ticker!] ? "Requested" : "Request Approval"}
                      </button>
                    )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
