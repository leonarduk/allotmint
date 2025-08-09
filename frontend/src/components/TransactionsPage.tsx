import { useMemo, useState } from "react";
import type { OwnerSummary, Transaction } from "../types";
import { getTransactions } from "../api";
import { useFetch } from "../hooks/useFetch";

type Props = {
  owners: OwnerSummary[];
};

export function TransactionsPage({ owners }: Props) {
  const [owner, setOwner] = useState("");
  const [account, setAccount] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const { data: transactions = [], loading, error } = useFetch<Transaction[]>(
    () =>
      getTransactions({
        owner: owner || undefined,
        account: account || undefined,
        start: start || undefined,
        end: end || undefined,
      }),
    [owner, account, start, end]
  );

  const accountOptions = useMemo(() => {
    if (owner) {
      return owners.find((o) => o.owner === owner)?.accounts ?? [];
    }
    const set = new Set<string>();
    owners.forEach((o) => o.accounts.forEach((a) => set.add(a)));
    return Array.from(set);
  }, [owner, owners]);

  return (
    <div>
      <div style={{ marginBottom: "1rem" }}>
        <label>
          Owner:
          <select value={owner} onChange={(e) => setOwner(e.target.value)}>
            <option value="">All</option>
            {owners.map((o) => (
              <option key={o.owner} value={o.owner}>
                {o.owner}
              </option>
            ))}
          </select>
        </label>
        <label style={{ marginLeft: "0.5rem" }}>
          Account:
          <select value={account} onChange={(e) => setAccount(e.target.value)}>
            <option value="">All</option>
            {accountOptions.map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>
        </label>
        <label style={{ marginLeft: "0.5rem" }}>
          Start: <input type="date" value={start} onChange={(e) => setStart(e.target.value)} />
        </label>
        <label style={{ marginLeft: "0.5rem" }}>
          End: <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
        </label>
      </div>

      {error && <p style={{ color: "red" }}>{error}</p>}
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
