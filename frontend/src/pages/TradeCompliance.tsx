import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { getOwners, getTransactionsWithCompliance, requestApproval } from "../api";
import type { OwnerSummary, TransactionWithCompliance } from "../types";
import { OwnerSelector } from "../components/OwnerSelector";
import { sanitizeOwners } from "../utils/owners";

export default function TradeCompliance() {
  const { t } = useTranslation();
  const { owner: ownerParam } = useParams<{ owner?: string }>();
  const navigate = useNavigate();
  const [owners, setOwners] = useState<OwnerSummary[]>([]);
  const [owner, setOwner] = useState(ownerParam ?? "");
  const [trades, setTrades] = useState<TransactionWithCompliance[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [requested, setRequested] = useState<Record<string, boolean>>({});

  useEffect(() => {
    getOwners()
      .then((os) => setOwners(sanitizeOwners(os)))
      .catch(() => setOwners([]));
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
      <h1>{t("tradeCompliance.title")}</h1>
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
              <th>{t("tradeCompliance.date")}</th>
              <th>{t("tradeCompliance.ticker")}</th>
              <th>{t("tradeCompliance.type")}</th>
              <th>{t("tradeCompliance.warnings")}</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {trades.map((trade, idx) => (
              <tr key={idx}>
                <td>{trade.date}</td>
                <td>{trade.ticker}</td>
                <td>{trade.type || trade.kind}</td>
                <td>{trade.warnings.join("; ")}</td>
                <td>
                  {trade.warnings.some((w) => w.includes("without approval")) &&
                    trade.ticker && (
                      <button
                        onClick={() => handleRequest(trade.ticker!)}
                        disabled={requested[trade.ticker!]}
                      >
                        {requested[trade.ticker!]
                          ? t("tradeCompliance.requested")
                          : t("tradeCompliance.requestApproval")}
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
