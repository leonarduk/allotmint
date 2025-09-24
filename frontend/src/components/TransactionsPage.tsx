import { useEffect, useMemo, useState, useCallback } from "react";
import type { ChangeEventHandler, FormEvent } from "react";
import type { OwnerSummary, Transaction } from "../types";
import { createTransaction, getTransactions } from "../api";
import { Selector } from "./Selector";
import { useFetch } from "../hooks/useFetch";
import tableStyles from "../styles/table.module.css";
import { money } from "../lib/money";
import { formatDateISO } from "../lib/date";
import { useConfig } from "../ConfigContext";
import { useTranslation } from "react-i18next";

type Props = {
  owners: OwnerSummary[];
};

export function TransactionsPage({ owners }: Props) {
  const [owner, setOwner] = useState("");
  const [account, setAccount] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);
  const [newOwner, setNewOwner] = useState("");
  const [newAccount, setNewAccount] = useState("");
  const [newDate, setNewDate] = useState("");
  const [newTicker, setNewTicker] = useState("");
  const [newPrice, setNewPrice] = useState("");
  const [newUnits, setNewUnits] = useState("");
  const [newFees, setNewFees] = useState("");
  const [newComments, setNewComments] = useState("");
  const [newReason, setNewReason] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [formSuccess, setFormSuccess] = useState<string | null>(null);
  const { t } = useTranslation();
  const { baseCurrency } = useConfig();
  const fetchTransactions = useCallback(
    () =>
      getTransactions({
        owner: owner || undefined,
        account: account || undefined,
        start: start || undefined,
        end: end || undefined,
      }),
    [owner, account, start, end, refreshKey]
  );
  const { data: transactions, loading, error } = useFetch<Transaction[]>(
    fetchTransactions,
    [owner, account, start, end, refreshKey]
  );

  const accountOptions = useMemo(() => {
    if (owner) {
      return owners.find((o) => o.owner === owner)?.accounts ?? [];
    }
    const set = new Set<string>();
    owners.forEach((o) => o.accounts.forEach((a) => set.add(a)));
    return Array.from(set);
  }, [owner, owners]);

  const newAccountOptions = useMemo(() => {
    if (!newOwner) {
      return [];
    }
    return owners.find((o) => o.owner === newOwner)?.accounts ?? [];
  }, [newOwner, owners]);

  useEffect(() => {
    if (!newOwner && owners.length === 1) {
      setNewOwner(owners[0].owner);
    }
    if (newOwner && !owners.some((o) => o.owner === newOwner)) {
      setNewOwner("");
    }
  }, [owners, newOwner]);

  useEffect(() => {
    if (!newOwner) {
      if (newAccount) {
        setNewAccount("");
      }
      return;
    }
    if (newAccountOptions.length === 0) {
      if (newAccount) {
        setNewAccount("");
      }
      return;
    }
    if (!newAccountOptions.includes(newAccount)) {
      const nextAccount = newAccountOptions[0] ?? "";
      if (nextAccount !== newAccount) {
        setNewAccount(nextAccount);
      }
    }
  }, [newOwner, newAccountOptions, newAccount]);

  const handleOwnerChange = useCallback<ChangeEventHandler<HTMLSelectElement>>(
    (e) => setOwner(e.target.value),
    [],
  );

  const handleAccountChange = useCallback<ChangeEventHandler<HTMLSelectElement>>(
    (e) => setAccount(e.target.value),
    [],
  );

  const setFilterOwnerAndAccount = useCallback(
    (nextOwner: string, nextAccount: string) => {
      setOwner(nextOwner);
      setAccount(nextAccount);
    },
    [],
  );

  const handleSubmit = useCallback(
    async (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      setFormError(null);
      setFormSuccess(null);

      const price = Number.parseFloat(newPrice);
      const units = Number.parseFloat(newUnits);
      const fees = newFees ? Number.parseFloat(newFees) : undefined;
      const ticker = newTicker.trim().toUpperCase();
      const reason = newReason.trim();
      const comments = newComments.trim();

      if (!newOwner || !newAccount || !newDate || !ticker || !reason) {
        setFormError("Please complete all required fields.");
        return;
      }
      if (!Number.isFinite(price) || price <= 0) {
        setFormError("Enter a valid price.");
        return;
      }
      if (!Number.isFinite(units) || units <= 0) {
        setFormError("Enter a valid number of units.");
        return;
      }
      if (newFees && (fees == null || Number.isNaN(fees))) {
        setFormError("Enter a valid fee or leave it blank.");
        return;
      }
      if (fees != null && fees < 0) {
        setFormError("Fees cannot be negative.");
        return;
      }

      setSubmitting(true);
      try {
        await createTransaction({
          owner: newOwner,
          account: newAccount,
          date: newDate,
          ticker,
          price_gbp: price,
          units,
          reason,
          fees,
          comments: comments || undefined,
        });
        setFormSuccess("Transaction created successfully.");
        setFilterOwnerAndAccount(newOwner, newAccount);
        setNewTicker("");
        setNewPrice("");
        setNewUnits("");
        setNewFees("");
        setNewComments("");
        setNewReason("");
        setNewDate("");
        setRefreshKey((key) => key + 1);
      } catch (err) {
        const message =
          err instanceof Error ? err.message : "Failed to create transaction.";
        setFormError(message);
      } finally {
        setSubmitting(false);
      }
    },
    [
      newOwner,
      newAccount,
      newDate,
      newTicker,
      newPrice,
      newUnits,
      newReason,
      newFees,
      newComments,
      setFilterOwnerAndAccount,
    ],
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

      <form
        onSubmit={handleSubmit}
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "0.75rem",
          alignItems: "flex-end",
          marginBottom: "1rem",
        }}
      >
        <Selector
          label="Owner"
          value={newOwner}
          onChange={(e) => setNewOwner(e.target.value)}
          options={[
            { value: "", label: "Select" },
            ...owners.map((o) => ({ value: o.owner, label: o.owner })),
          ]}
        />
        <Selector
          label="Account"
          value={newAccount}
          onChange={(e) => setNewAccount(e.target.value)}
          options={[
            { value: "", label: newOwner ? "Select" : "Select owner first" },
            ...newAccountOptions.map((a) => ({ value: a, label: a })),
          ]}
        />
        <label style={{ display: "flex", flexDirection: "column" }}>
          Date
          <input
            type="date"
            value={newDate}
            onChange={(e) => setNewDate(e.target.value)}
            required
          />
        </label>
        <label style={{ display: "flex", flexDirection: "column" }}>
          Ticker
          <input
            type="text"
            value={newTicker}
            onChange={(e) => setNewTicker(e.target.value.toUpperCase())}
            placeholder="e.g. VUSA"
            required
          />
        </label>
        <label style={{ display: "flex", flexDirection: "column" }}>
          Price (GBP)
          <input
            type="number"
            step="0.01"
            min="0"
            value={newPrice}
            onChange={(e) => setNewPrice(e.target.value)}
            required
          />
        </label>
        <label style={{ display: "flex", flexDirection: "column" }}>
          Units
          <input
            type="number"
            step="0.0001"
            min="0"
            value={newUnits}
            onChange={(e) => setNewUnits(e.target.value)}
            required
          />
        </label>
        <label style={{ display: "flex", flexDirection: "column" }}>
          Fees (GBP)
          <input
            type="number"
            step="0.01"
            min="0"
            value={newFees}
            onChange={(e) => setNewFees(e.target.value)}
          />
        </label>
        <label style={{ display: "flex", flexDirection: "column", minWidth: "180px" }}>
          Reason
          <input
            type="text"
            value={newReason}
            onChange={(e) => setNewReason(e.target.value)}
            required
          />
        </label>
        <label style={{ display: "flex", flexDirection: "column", minWidth: "180px" }}>
          Comments
          <input
            type="text"
            value={newComments}
            onChange={(e) => setNewComments(e.target.value)}
            placeholder="Optional"
          />
        </label>
        <button type="submit" disabled={submitting} style={{ height: "2.3rem" }}>
          {submitting ? "Saving..." : "Add transaction"}
        </button>
      </form>

      {formError && <p style={{ color: "red" }}>{formError}</p>}
      {formSuccess && <p style={{ color: "limegreen" }}>{formSuccess}</p>}

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
              <th className={tableStyles.cell}>Instrument</th>
              <th className={tableStyles.cell}>Type</th>
              <th className={`${tableStyles.cell} ${tableStyles.right}`}>Amount</th>
              <th className={`${tableStyles.cell} ${tableStyles.right}`}>Shares</th>
            </tr>
          </thead>
          <tbody>
            {(transactions ?? []).map((t, i) => (
              <tr key={i}>
                <td className={tableStyles.cell}>
                {t.date ? formatDateISO(new Date(t.date)) : ""}
                </td>
                <td className={tableStyles.cell}>{t.owner}</td>
                <td className={tableStyles.cell}>{t.account}</td>
                <td className={tableStyles.cell}>{t.ticker || t.security_ref || ""}</td>
                <td className={tableStyles.cell}>{t.type || t.kind}</td>
                <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                  {t.amount_minor != null
                    ? money(t.amount_minor / 100, t.currency ?? baseCurrency)
                    : t.price_gbp != null && t.units != null
                    ? money(t.price_gbp * t.units, baseCurrency)
                    : ""}
                </td>
                <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                  {t.shares ?? t.units ?? ""}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
