import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { complianceForOwner, getOwners } from "../api";
import type { OwnerSummary, ComplianceResult } from "../types";
import { OwnerSelector } from "../components/OwnerSelector";

export default function ComplianceWarnings() {
  const { owner: ownerParam } = useParams<{ owner?: string }>();
  const navigate = useNavigate();
  const [owners, setOwners] = useState<OwnerSummary[]>([]);
  const [owner, setOwner] = useState(ownerParam ?? "");
  const [result, setResult] = useState<ComplianceResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getOwners().then(setOwners).catch(() => setOwners([]));
  }, []);

  useEffect(() => {
    if (!owner) {
      setResult(null);
      return;
    }
    complianceForOwner(owner)
      .then((res) => {
        setResult(res);
        setError(null);
      })
      .catch((e) => {
        setResult(null);
        setError(e instanceof Error ? e.message : String(e));
      });
  }, [owner]);

  return (
    <div style={{ maxWidth: 900, margin: "0 auto", padding: "1rem" }}>
      <h1>Compliance warnings</h1>
      <OwnerSelector
        owners={owners}
        selected={owner}
        onSelect={(o) => {
          setOwner(o);
          navigate(`/compliance/${o}`);
        }}
      />
      {error && <p style={{ color: "red" }}>{error}</p>}
      {result && (
        <>
          {result.warnings.length ? (
            <ul>
              {result.warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          ) : (
            <p>No warnings.</p>
          )}

          {result.hold_countdowns &&
            Object.keys(result.hold_countdowns).length > 0 && (
              <div style={{ marginTop: "1rem" }}>
                <h2>Holding periods</h2>
                <ul>
                  {Object.entries(result.hold_countdowns).map(([t, d]) => (
                    <li key={t}>
                      {t}: {d} day{d === 1 ? "" : "s"} remaining
                    </li>
                  ))}
                </ul>
              </div>
            )}

          {typeof result.trades_remaining === "number" && (
            <div style={{ marginTop: "1rem" }}>
                {(() => {
                  const key = new Date().toISOString().slice(0, 7);
                  const used = result.trade_counts?.[key] ?? 0;
                  const max = used + (result.trades_remaining ?? 0);
                  return (
                    <p>
                      Trades this month: {used} / {max} ({result.trades_remaining} remaining)
                    </p>
                  );
                })()}
              </div>
            )}
          </>
        )}
      </div>
  );
}
