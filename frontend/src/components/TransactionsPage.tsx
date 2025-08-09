import { useEffect, useMemo, useState } from "react";
import type { OwnerSummary, Transaction } from "../types";
import { getTransactions } from "../api";
import { Selector } from "./Selector";

type Props = {
  owners: OwnerSummary[];
};

export function TransactionsPage({ owners }: Props) {
  const [owner, setOwner] = useState("");
  const [account, setAccount] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const accountOptions = useMemo(() => {
    if (owner) {
      return owners.find((o) => o.owner === owner)?.accounts ?? [];
    }
    const set = new Set<string>();
    owners.forEach((o) => o.accounts.forEach((a) => set.add(a)));
    return Array.from(set);
  }, [owner, owners]);

  useEffect(() => {
    setLoading(true);
    setErr(null);
    getTransactions({
      owner: owner || undefined,
      account: account || undefined,
      start: start || undefined,
      end: end || undefined,
    })
      .then(setTransactions)
      .catch((e) => setErr(String(e)))
      .finally(() => setLoading(false));
  }, [owner, account, start, end]);

  return (
    <div>
      <div style={{ marginBottom: "1rem" }}>
        <Selector
          label="Owner"
          value={owner}
          onChange={setOwner}
          options={[
            { value: "", label: "All" },
            ...owners.map((o) => ({ value: o.owner, label: o.owner })),
          ]}
        />
        <Selector
          label="Account"
          value={account}
          onChange={setAccount}
          options={[
            { value: "", label: "All" },
            ...accountOptions.map((a) => ({ value: a, label: a })),
          ]}
        />
        <label style={{ marginLeft: "0.5rem" }}>
          Start: <input type="date" value={start} onChange={(e) => setStart(e.target.value)} />
        </label>
        <label style={{ marginLeft: "0.5rem" }}>
          End: <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
        </label>
      </div>

      {err && <p style={{ color: "red" }}>{err}</p>}
      {loading ? (
        <p>Loading…</p>
      ) : (
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <th style={{ textAlign: "left" }}>Date</th>
              <th style={{ textAlign: "left" }}>Owner</th>
              <th style={{ textAlign: "left" }}>Account</th>
              <th style={{ textAlign: "left" }}>Type</th>
              <th style={{ textAlign: "right" }}>Amount</th>
              <th style={{ textAlign: "right" }}>Shares</th>
            </tr>
          </thead>
          <tbody>
            {transactions.map((t, i) => (
              <tr key={i}>
                <td>{t.date ? new Date(t.date).toLocaleDateString() : ""}</td>
                <td>{t.owner}</td>
                <td>{t.account}</td>
                <td>{t.type || t.kind}</td>
                <td style={{ textAlign: "right" }}>
                  {t.amount_minor != null ? (t.amount_minor / 100).toFixed(2) : ""}
                </td>
                <td style={{ textAlign: "right" }}>{t.shares ?? ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
