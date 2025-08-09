import { useMemo, useState } from "react";
import type { OwnerSummary, Transaction } from "../types";
import { getTransactions } from "../api";
import { Selector } from "./Selector";
import { useFetch } from "../hooks/useFetch";
import tableStyles from "../styles/table.module.css";

type Props = {
  owners: OwnerSummary[];
};

export function TransactionsPage({ owners }: Props) {
  const [owner, setOwner] = useState("");
  const [account, setAccount] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const { data: transactions, loading, error } = useFetch<Transaction[]>(
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

      {error && <p style={{ color: "red" }}>{error.message}</p>}
      {loading ? (
        <p>Loading…</p>
      ) : (
        <table className={tableStyles.table}>
          <thead>
            <tr>
              <th className={tableStyles.cell}>Date</th>
              <th className={tableStyles.cell}>Owner</th>
              <th className={tableStyles.cell}>Account</th>
              <th className={tableStyles.cell}>Type</th>
              <th className={`${tableStyles.cell} ${tableStyles.right}`}>Amount</th>
              <th className={`${tableStyles.cell} ${tableStyles.right}`}>Shares</th>
            </tr>
          </thead>
          <tbody>
            {(transactions ?? []).map((t, i) => (
              <tr key={i}>
                <td className={tableStyles.cell}>{t.date ? new Date(t.date).toLocaleDateString() : ""}</td>
                <td className={tableStyles.cell}>{t.owner}</td>
                <td className={tableStyles.cell}>{t.account}</td>
                <td className={tableStyles.cell}>{t.type || t.kind}</td>
                <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                  {t.amount_minor != null ? (t.amount_minor / 100).toFixed(2) : ""}
                </td>
                <td className={`${tableStyles.cell} ${tableStyles.right}`}>{t.shares ?? ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
