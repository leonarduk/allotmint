import { useMemo, useState, useCallback } from "react";
import type { ChangeEventHandler } from "react";
import type { OwnerSummary, Transaction } from "../types";
import { getTransactions } from "../api";
import { Selector } from "./Selector";
import { useFetch } from "../hooks/useFetch";
import tableStyles from "../styles/table.module.css";
import { money } from "../lib/money";
import i18n from "../i18n";
import { useTranslation } from "react-i18next";

type Props = {
  owners: OwnerSummary[];
};

export function TransactionsPage({ owners }: Props) {
  const [owner, setOwner] = useState("");
  const [account, setAccount] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const { t } = useTranslation();
  const fetchTransactions = useCallback(
    () =>
      getTransactions({
        owner: owner || undefined,
        account: account || undefined,
        start: start || undefined,
        end: end || undefined,
      }),
    [owner, account, start, end]
  );
  const { data: transactions, loading, error } = useFetch<Transaction[]>(
    fetchTransactions,
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

  const handleOwnerChange = useCallback<ChangeEventHandler<HTMLSelectElement>>(
    (e) => setOwner(e.target.value),
    [],
  );

  const handleAccountChange = useCallback<ChangeEventHandler<HTMLSelectElement>>(
    (e) => setAccount(e.target.value),
    [],
  );

  return (
    <div>
      <div style={{ marginBottom: "1rem" }}>
        <Selector
          label={t("owner.label")}
          value={owner}
          onChange={handleOwnerChange}
          options={[
            { value: "", label: "All" },
            ...owners.map((o) => ({ value: o.owner, label: o.owner })),
          ]}
        />
        <Selector
          label="Account"
          value={account}
          onChange={handleAccountChange}
          options={[
            { value: "", label: "All" },
            ...accountOptions.map((a) => ({ value: a, label: a })),
          ]}
        />
        <label style={{ marginLeft: "0.5rem" }}>
          {t("query.start")}: <input type="date" value={start} onChange={(e) => setStart(e.target.value)} />
        </label>
        <label style={{ marginLeft: "0.5rem" }}>
          {t("query.end")}: <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
        </label>
      </div>

      {error && <p style={{ color: "red" }}>{error.message}</p>}
      {loading ? (
        <p>{t("common.loading")}</p>
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
                <td className={tableStyles.cell}>
                  {t.date
                    ? new Intl.DateTimeFormat(i18n.language).format(
                        new Date(t.date),
                      )
                    : ""}
                </td>
                <td className={tableStyles.cell}>{t.owner}</td>
                <td className={tableStyles.cell}>{t.account}</td>
                <td className={tableStyles.cell}>{t.type || t.kind}</td>
                <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                  {t.amount_minor != null
                    ? money(t.amount_minor / 100, t.currency ?? "GBP")
                    : ""}
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
