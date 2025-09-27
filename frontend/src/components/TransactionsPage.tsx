import { useEffect, useMemo, useState, useCallback } from "react";
import type { ChangeEventHandler, FormEvent } from "react";
import type { OwnerSummary, Transaction } from "../types";
import {
  createTransaction,
  deleteTransaction,
  getTransactions,
  updateTransaction,
} from "../api";
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
  const [editingId, setEditingId] = useState<string | null>(null);
  const [pageSize, setPageSize] = useState(20);
  const [currentPage, setCurrentPage] = useState(0);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const { t } = useTranslation();
  const { baseCurrency } = useConfig();
  const pageSizeOptions = [10, 20, 50, 100];

  const resetForm = useCallback(() => {
    setNewTicker("");
    setNewPrice("");
    setNewUnits("");
    setNewFees("");
    setNewComments("");
    setNewReason("");
    setNewDate("");
  }, []);
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

  const totalTransactions = transactions?.length ?? 0;
  const maxPageIndex = Math.max(Math.ceil(totalTransactions / pageSize) - 1, 0);
  const clampedPage = Math.min(currentPage, maxPageIndex);
  const totalPages = totalTransactions === 0 ? 1 : Math.ceil(totalTransactions / pageSize);

  useEffect(() => {
    if (currentPage !== clampedPage) {
      setCurrentPage(clampedPage);
    }
  }, [clampedPage, currentPage]);

  useEffect(() => {
    setCurrentPage(0);
  }, [owner, account, start, end]);

  useEffect(() => {
    setCurrentPage(0);
  }, [pageSize]);

  const paginatedTransactions = useMemo(() => {
    if (!transactions) {
      return [];
    }
    const startIndex = clampedPage * pageSize;
    return transactions.slice(startIndex, startIndex + pageSize);
  }, [transactions, clampedPage, pageSize]);

  const transactionById = useMemo(() => {
    const map = new Map<string, Transaction>();
    transactions?.forEach((tx) => {
      if (tx.id) {
        map.set(tx.id, tx);
      }
    });
    return map;
  }, [transactions]);

  const selectedCount = selectedIds.length;
  const hasSelection = selectedCount > 0;
  const allPageIds = useMemo(
    () =>
      paginatedTransactions
        .map((tx) => tx.id)
        .filter((id): id is string => Boolean(id)),
    [paginatedTransactions],
  );
  const isAllPageSelected =
    allPageIds.length > 0 && allPageIds.every((id) => selectedIds.includes(id));

  useEffect(() => {
    if (!transactions || transactions.length === 0) {
      if (selectedIds.length > 0) {
        setSelectedIds([]);
      }
      return;
    }
    const validIds = new Set(
      transactions.map((tx) => tx.id).filter((id): id is string => Boolean(id)),
    );
    setSelectedIds((prev) => prev.filter((id) => validIds.has(id)));
  }, [transactions]);

  const pageStart = totalTransactions === 0 ? 0 : clampedPage * pageSize + 1;
  const pageEnd =
    totalTransactions === 0
      ? 0
      : Math.min(totalTransactions, (clampedPage + 1) * pageSize);
  const isFirstPage = clampedPage === 0;
  const isLastPage = totalTransactions === 0 || clampedPage >= maxPageIndex;
  const currentPageDisplay = totalTransactions === 0 ? 0 : clampedPage + 1;
  const showingRangeLabel =
    totalTransactions === 0
      ? "Showing 0 of 0"
      : `Showing ${pageStart}-${pageEnd} of ${totalTransactions}`;
  const totalPagesDisplay = totalTransactions === 0 ? 0 : totalPages;

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

  const handleToggleSelect = useCallback((txId: string, checked: boolean) => {
    setSelectedIds((prev) => {
      if (checked) {
        if (prev.includes(txId)) {
          return prev;
        }
        return [...prev, txId];
      }
      return prev.filter((id) => id !== txId);
    });
  }, []);

  const handleToggleSelectAllOnPage = useCallback(
    (checked: boolean) => {
      if (!checked) {
        setSelectedIds((prev) => prev.filter((id) => !allPageIds.includes(id)));
        return;
      }
      setSelectedIds((prev) => {
        const next = new Set(prev);
        allPageIds.forEach((id) => next.add(id));
        return Array.from(next);
      });
    },
    [allPageIds],
  );

  const handlePageSizeChange = useCallback<ChangeEventHandler<HTMLSelectElement>>(
    (event) => {
      setPageSize(Number(event.target.value));
    },
    [],
  );

  const handlePreviousPage = useCallback(() => {
    setCurrentPage((page) => Math.max(page - 1, 0));
  }, []);

  const handleNextPage = useCallback(() => {
    setCurrentPage((page) => page + 1);
  }, []);

  const handleEdit = useCallback(
    (tx: Transaction) => {
      if (!tx.id) {
        return;
      }
      setEditingId(tx.id);
      setNewOwner(tx.owner);
      setNewAccount(tx.account);
      setNewDate(tx.date ? tx.date.slice(0, 10) : "");
      const tickerValue = (tx.ticker ?? tx.security_ref ?? "").toUpperCase();
      setNewTicker(tickerValue);
      const unitsValue = tx.units ?? tx.shares ?? null;
      const numericUnits =
        typeof unitsValue === "number"
          ? unitsValue
          : unitsValue != null
          ? Number(unitsValue)
          : null;
      setNewUnits(numericUnits != null ? String(numericUnits) : "");
      const priceValue =
        tx.price_gbp != null
          ? tx.price_gbp
          : tx.amount_minor != null && numericUnits
          ? tx.amount_minor / 100 / numericUnits
          : null;
      setNewPrice(
        priceValue != null && Number.isFinite(priceValue)
          ? String(priceValue)
          : "",
      );
      setNewFees(tx.fees != null ? String(tx.fees) : "");
      setNewComments(tx.comments ?? "");
      const legacyReason = (tx as { reason_to_buy?: string | null }).reason_to_buy;
      setNewReason(tx.reason ?? legacyReason ?? "");
      setFormError(null);
      setFormSuccess(null);
    },
    [],
  );

  const handleCancelEdit = useCallback(() => {
    setEditingId(null);
    resetForm();
    setFormError(null);
    setFormSuccess(null);
  }, [resetForm]);

  const handleDelete = useCallback(
    async (tx: Transaction) => {
      if (!tx.id) {
        return;
      }
      if (typeof window !== "undefined" && !window.confirm("Delete this transaction?")) {
        return;
      }
      setFormError(null);
      setFormSuccess(null);
      try {
        await deleteTransaction(tx.id);
        if (editingId === tx.id) {
          setEditingId(null);
          resetForm();
        }
        setFormSuccess("Transaction deleted successfully.");
        setFilterOwnerAndAccount(tx.owner, tx.account ?? "");
        setRefreshKey((key) => key + 1);
      } catch (err) {
        const message =
          err instanceof Error ? err.message : "Failed to delete transaction.";
        setFormError(message);
      }
    },
    [editingId, resetForm, setFilterOwnerAndAccount],
  );

  const buildPayload = useCallback(() => {
    const price = Number.parseFloat(newPrice);
    const units = Number.parseFloat(newUnits);
    const fees = newFees ? Number.parseFloat(newFees) : undefined;
    const ticker = newTicker.trim().toUpperCase();
    const reason = newReason.trim();
    const comments = newComments.trim();

    if (!newOwner || !newAccount || !newDate || !ticker || !reason) {
      setFormError("Please complete all required fields.");
      return null;
    }
    if (!Number.isFinite(price) || price <= 0) {
      setFormError("Enter a valid price.");
      return null;
    }
    if (!Number.isFinite(units) || units <= 0) {
      setFormError("Enter a valid number of units.");
      return null;
    }
    if (newFees && (fees == null || Number.isNaN(fees))) {
      setFormError("Enter a valid fee or leave it blank.");
      return null;
    }
    if (fees != null && fees < 0) {
      setFormError("Fees cannot be negative.");
      return null;
    }

    return {
      payload: {
        owner: newOwner,
        account: newAccount,
        date: newDate,
        ticker,
        price_gbp: price,
        units,
        reason,
        fees,
        comments: comments || undefined,
      },
    } as const;
  }, [
    newOwner,
    newAccount,
    newDate,
    newTicker,
    newPrice,
    newUnits,
    newReason,
    newFees,
    newComments,
    setFormError,
  ]);

  const handleBulkDelete = useCallback(async () => {
    if (!hasSelection) {
      return;
    }
    if (
      typeof window !== "undefined" &&
      !window.confirm(
        `Delete ${selectedCount} selected transaction${selectedCount === 1 ? "" : "s"}?`,
      )
    ) {
      return;
    }
    setFormError(null);
    setFormSuccess(null);
    try {
      await Promise.all(selectedIds.map((id) => deleteTransaction(id)));
      if (editingId && selectedIds.includes(editingId)) {
        setEditingId(null);
        resetForm();
      }
      const firstSelected = selectedIds[0]
        ? transactionById.get(selectedIds[0])
        : null;
      if (firstSelected) {
        setFilterOwnerAndAccount(firstSelected.owner, firstSelected.account ?? "");
      }
      setSelectedIds([]);
      setFormSuccess(
        `Deleted ${selectedCount} transaction${selectedCount === 1 ? "" : "s"} successfully.`,
      );
      setRefreshKey((key) => key + 1);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Failed to delete selected transactions.";
      setFormError(message);
    }
  }, [
    editingId,
    hasSelection,
    resetForm,
    selectedCount,
    selectedIds,
    setFilterOwnerAndAccount,
    transactionById,
    setFormError,
    setFormSuccess,
    setRefreshKey,
    setSelectedIds,
  ]);

  const handleApplyToSelected = useCallback(async () => {
    if (!hasSelection) {
      return;
    }
    const result = buildPayload();
    if (!result) {
      return;
    }
    if (
      typeof window !== "undefined" &&
      !window.confirm(
        `Update ${selectedCount} selected transaction${selectedCount === 1 ? "" : "s"}?`,
      )
    ) {
      return;
    }
    setFormError(null);
    setFormSuccess(null);
    setSubmitting(true);
    try {
      await Promise.all(selectedIds.map((id) => updateTransaction(id, result.payload)));
      if (editingId && selectedIds.includes(editingId)) {
        setEditingId(null);
      }
      setFilterOwnerAndAccount(result.payload.owner, result.payload.account);
      setSelectedIds([]);
      setFormSuccess(
        `Updated ${selectedCount} transaction${selectedCount === 1 ? "" : "s"} successfully.`,
      );
      setRefreshKey((key) => key + 1);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Failed to update selected transactions.";
      setFormError(message);
    } finally {
      setSubmitting(false);
    }
  }, [
    buildPayload,
    editingId,
    hasSelection,
    selectedCount,
    selectedIds,
    setFilterOwnerAndAccount,
    setFormError,
    setFormSuccess,
    setRefreshKey,
    setSelectedIds,
    setSubmitting,
  ]);

  const handleSubmit = useCallback(
    async (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      setFormError(null);
      setFormSuccess(null);

      const result = buildPayload();
      if (!result) {
        return;
      }
      setSubmitting(true);
      try {
        if (editingId) {
          await updateTransaction(editingId, result.payload);
          setFormSuccess("Transaction updated successfully.");
          setEditingId(null);
        } else {
          await createTransaction(result.payload);
          setFormSuccess("Transaction created successfully.");
        }
        setFilterOwnerAndAccount(result.payload.owner, result.payload.account);
        resetForm();
        setRefreshKey((key) => key + 1);
      } catch (err) {
        const message =
          err instanceof Error
            ? err.message
            : editingId
            ? "Failed to update transaction."
            : "Failed to create transaction.";
        setFormError(message);
      } finally {
        setSubmitting(false);
      }
    },
    [buildPayload, setFilterOwnerAndAccount, editingId, resetForm, setRefreshKey],
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
          {submitting
            ? editingId
              ? "Updating..."
              : "Saving..."
            : editingId
            ? "Update transaction"
            : "Add transaction"}
        </button>
        {editingId && (
          <button
            type="button"
            onClick={handleCancelEdit}
            disabled={submitting}
            style={{ height: "2.3rem" }}
          >
            Cancel
          </button>
        )}
        <button
          type="button"
          onClick={handleApplyToSelected}
          disabled={!hasSelection || submitting}
          style={{ height: "2.3rem" }}
        >
          Apply to selected{hasSelection ? ` (${selectedCount})` : ""}
        </button>
      </form>

      {editingId && (
        <p style={{ color: "#ffd24d" }}>Editing existing transaction. Save or cancel to finish.</p>
      )}

      {formError && <p style={{ color: "red" }}>{formError}</p>}
      {formSuccess && <p style={{ color: "limegreen" }}>{formSuccess}</p>}

      {error && <p style={{ color: "red" }}>{error.message}</p>}
      {loading ? (
        <p>{t("common.loading")}</p>
      ) : (
        <>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: "0.5rem",
              flexWrap: "wrap",
              gap: "0.75rem",
            }}
          >
            <label>
              Rows per page:
              <select
                value={pageSize}
                onChange={handlePageSizeChange}
                style={{ marginLeft: "0.5rem" }}
              >
                {pageSizeOptions.map((size) => (
                  <option key={size} value={size}>
                    {size}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              onClick={handleBulkDelete}
              disabled={!hasSelection}
            >
              Delete selected{hasSelection ? ` (${selectedCount})` : ""}
            </button>
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <span>{showingRangeLabel}</span>
              <button type="button" onClick={handlePreviousPage} disabled={isFirstPage}>
                Previous
              </button>
              <span>
                Page {currentPageDisplay} of {totalPagesDisplay}
              </span>
              <button type="button" onClick={handleNextPage} disabled={isLastPage}>
                Next
              </button>
            </div>
          </div>
          <table className={tableStyles.table}>
            <thead>
              <tr>
                <th className={tableStyles.cell}>
                  <input
                    type="checkbox"
                    checked={isAllPageSelected && allPageIds.length > 0}
                    disabled={allPageIds.length === 0}
                    onChange={(e) => handleToggleSelectAllOnPage(e.target.checked)}
                    aria-label="Select all transactions on this page"
                  />
                </th>
                <th className={tableStyles.cell}>Date</th>
                <th className={tableStyles.cell}>Owner</th>
                <th className={tableStyles.cell}>Account</th>
                <th className={tableStyles.cell}>Instrument</th>
                <th className={tableStyles.cell}>Instrument name</th>
                <th className={tableStyles.cell}>Type</th>
                <th className={`${tableStyles.cell} ${tableStyles.right}`}>Amount</th>
                <th className={`${tableStyles.cell} ${tableStyles.right}`}>Shares</th>
                <th className={tableStyles.cell}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {paginatedTransactions.length === 0 ? (
                <tr>
                  <td
                    className={tableStyles.cell}
                    colSpan={9}
                    style={{ textAlign: "center" }}
                  >
                    No transactions found.
                  </td>
                </tr>
              ) : (
                paginatedTransactions.map((t, i) => {
                  const key = t.id ?? `${t.owner}-${t.date ?? ""}-${i}`;
                  return (
                    <tr key={key}>
                      <td className={tableStyles.cell}>
                        <input
                          type="checkbox"
                          disabled={!t.id}
                          checked={t.id ? selectedIds.includes(t.id) : false}
                          onChange={(e) =>
                            t.id && handleToggleSelect(t.id, e.target.checked)
                          }
                          aria-label={`Select transaction ${t.id ?? key}`}
                        />
                      </td>
                      <td className={tableStyles.cell}>
                        {t.date ? formatDateISO(new Date(t.date)) : ""}
                      </td>
                      <td className={tableStyles.cell}>{t.owner}</td>
                      <td className={tableStyles.cell}>{t.account}</td>
                      <td className={tableStyles.cell}>{t.ticker || t.security_ref || ""}</td>
                      <td className={tableStyles.cell}>{t.instrument_name || ""}</td>
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
                      <td className={tableStyles.cell}>
                        <div style={{ display: "flex", gap: "0.5rem" }}>
                          <button
                            type="button"
                            onClick={() => handleEdit(t)}
                            disabled={!t.id}
                          >
                            Edit
                          </button>
                          <button
                            type="button"
                            onClick={() => handleDelete(t)}
                            disabled={!t.id}
                          >
                            Delete
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}
