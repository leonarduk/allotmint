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
        result.warnings.length ? (
          <ul>
            {result.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        ) : (
          <p>No warnings.</p>
        )
      )}
    </div>
  );
}
