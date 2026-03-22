import { useCallback, useEffect, useMemo, useState, type ChangeEventHandler, type FormEvent } from "react";
import {
  createTransaction,
  deleteTransaction,
  getTransactions,
  updateTransaction,
} from "../../api";
import { useFetch } from "../../hooks/useFetch";
import type { OwnerSummary, Transaction } from "../../types";
import {
  buildShowingRangeLabel,
  buildTransactionPayload,
  createEmptyTransactionFormState,
  createTransactionFormStateFromTransaction,
  paginateTransactions,
  type TransactionFormState,
} from "./helpers";

export function useTransactionsController(owners: OwnerSummary[]) {
  const [filters, setFilters] = useState({ owner: "", account: "", start: "", end: "" });
  const [refreshKey, setRefreshKey] = useState(0);
  const [form, setForm] = useState<TransactionFormState>(createEmptyTransactionFormState);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [formSuccess, setFormSuccess] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [pageSize, setPageSize] = useState(20);
  const [currentPage, setCurrentPage] = useState(0);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);

  const fetchTransactions = useCallback(
    () =>
      getTransactions({
        owner: filters.owner || undefined,
        account: filters.account || undefined,
        start: filters.start || undefined,
        end: filters.end || undefined,
      }),
    [filters.account, filters.end, filters.owner, filters.start],
  );

  const { data: transactions, loading, error } = useFetch<Transaction[]>(
    fetchTransactions,
    [filters.owner, filters.account, filters.start, filters.end, refreshKey],
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
  }, [filters.owner, filters.account, filters.start, filters.end, pageSize]);

  const paginatedTransactions = useMemo(
    () => paginateTransactions(transactions, clampedPage, pageSize),
    [transactions, clampedPage, pageSize],
  );

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
    () => paginatedTransactions.map((tx) => tx.id).filter((id): id is string => Boolean(id)),
    [paginatedTransactions],
  );
  const isAllPageSelected =
    allPageIds.length > 0 && allPageIds.every((id) => selectedIds.includes(id));

  useEffect(() => {
    if (!transactions?.length) {
      if (selectedIds.length > 0) {
        setSelectedIds([]);
      }
      return;
    }
    const validIds = new Set(
      transactions.map((tx) => tx.id).filter((id): id is string => Boolean(id)),
    );
    setSelectedIds((prev) => prev.filter((id) => validIds.has(id)));
  }, [transactions, selectedIds.length]);

  const accountOptions = useMemo(() => {
    if (filters.owner) {
      return owners.find((owner) => owner.owner === filters.owner)?.accounts ?? [];
    }
    const set = new Set<string>();
    owners.forEach((owner) => owner.accounts.forEach((account) => set.add(account)));
    return Array.from(set);
  }, [filters.owner, owners]);

  const newAccountOptions = useMemo(() => {
    if (!form.owner) {
      return [];
    }
    return owners.find((owner) => owner.owner === form.owner)?.accounts ?? [];
  }, [form.owner, owners]);

  useEffect(() => {
    if (!form.owner && owners.length === 1) {
      setForm((prev) => ({ ...prev, owner: owners[0]?.owner ?? "" }));
    }
  }, [form.owner, owners]);

  useEffect(() => {
    if (!form.owner) {
      if (form.account) {
        setForm((prev) => ({ ...prev, account: "" }));
      }
      return;
    }
    if (newAccountOptions.length === 0) {
      if (form.account) {
        setForm((prev) => ({ ...prev, account: "" }));
      }
      return;
    }
    if (!newAccountOptions.includes(form.account)) {
      setForm((prev) => ({ ...prev, account: newAccountOptions[0] ?? "" }));
    }
  }, [form.owner, form.account, newAccountOptions]);

  const setFilterField = useCallback((key: keyof typeof filters, value: string) => {
    setFilters((prev) => ({ ...prev, [key]: value }));
  }, []);

  const setFormField = useCallback((key: keyof TransactionFormState, value: string) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  }, []);

  const handleOwnerChange = useCallback<ChangeEventHandler<HTMLSelectElement>>(
    (event) => setFilterField("owner", event.target.value),
    [setFilterField],
  );

  const handleAccountChange = useCallback<ChangeEventHandler<HTMLSelectElement>>(
    (event) => setFilterField("account", event.target.value),
    [setFilterField],
  );

  const setFilterOwnerAndAccount = useCallback((owner: string, account: string) => {
    setFilters((prev) => ({ ...prev, owner, account }));
  }, []);

  const resetForm = useCallback(() => {
    setForm((prev) => ({
      ...createEmptyTransactionFormState(),
      owner: prev.owner,
      account: prev.account,
    }));
  }, []);

  const startEditing = useCallback((transaction: Transaction) => {
    if (!transaction.id) {
      return;
    }
    setEditingId(transaction.id);
    setForm(createTransactionFormStateFromTransaction(transaction));
    setFormError(null);
    setFormSuccess(null);
  }, []);

  const cancelEditing = useCallback(() => {
    setEditingId(null);
    resetForm();
    setFormError(null);
    setFormSuccess(null);
  }, [resetForm]);

  const handleToggleSelect = useCallback((txId: string, checked: boolean) => {
    setSelectedIds((prev) => {
      if (checked) {
        return prev.includes(txId) ? prev : [...prev, txId];
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
      setSelectedIds((prev) => Array.from(new Set([...prev, ...allPageIds])));
    },
    [allPageIds],
  );

  const handlePageSizeChange = useCallback<ChangeEventHandler<HTMLSelectElement>>(
    (event) => setPageSize(Number(event.target.value)),
    [],
  );

  const handlePreviousPage = useCallback(() => {
    setCurrentPage((page) => Math.max(page - 1, 0));
  }, []);

  const handleNextPage = useCallback(() => {
    setCurrentPage((page) => page + 1);
  }, []);

  const createPayload = useCallback(() => {
    const result = buildTransactionPayload(form);
    if (!result.ok) {
      setFormError(result.error);
      return null;
    }
    return result.payload;
  }, [form]);

  const deleteOne = useCallback(
    async (transaction: Transaction) => {
      if (!transaction.id) {
        return;
      }
      if (typeof window !== "undefined" && !window.confirm("Delete this transaction?")) {
        return;
      }
      setFormError(null);
      setFormSuccess(null);
      try {
        await deleteTransaction(transaction.id);
        if (editingId === transaction.id) {
          setEditingId(null);
          resetForm();
        }
        setFormSuccess("Transaction deleted successfully.");
        setFilterOwnerAndAccount(transaction.owner, transaction.account ?? "");
        setRefreshKey((key) => key + 1);
      } catch (err) {
        setFormError(err instanceof Error ? err.message : "Failed to delete transaction.");
      }
    },
    [editingId, resetForm, setFilterOwnerAndAccount],
  );

  const bulkDelete = useCallback(async () => {
    if (!hasSelection) {
      return;
    }
    if (
      typeof window !== "undefined" &&
      !window.confirm(`Delete ${selectedCount} selected transaction${selectedCount === 1 ? "" : "s"}?`)
    ) {
      return;
    }
    setFormError(null);
    setFormSuccess(null);
    try {
      const groupedIds = new Map<string, { entries: { id: string; index: number }[] }>();
      const fallbackIds: string[] = [];
      selectedIds.forEach((id) => {
        const [ownerPart, accountPart, indexPart] = id.split(":");
        const parsedIndex = Number.parseInt(indexPart ?? "", 10);
        if (!ownerPart || !accountPart || Number.isNaN(parsedIndex)) {
          fallbackIds.push(id);
          return;
        }
        const key = `${ownerPart}:${accountPart}`;
        const group = groupedIds.get(key) ?? { entries: [] };
        group.entries.push({ id, index: parsedIndex });
        groupedIds.set(key, group);
      });
      const deletionOrder: string[] = [];
      groupedIds.forEach((group) => {
        group.entries.sort((a, b) => b.index - a.index).forEach(({ id }) => deletionOrder.push(id));
      });
      deletionOrder.push(...fallbackIds);
      for (const id of deletionOrder) {
        await deleteTransaction(id);
      }
      if (editingId && selectedIds.includes(editingId)) {
        setEditingId(null);
        resetForm();
      }
      const firstSelected = selectedIds[0] ? transactionById.get(selectedIds[0]) : null;
      if (firstSelected) {
        setFilterOwnerAndAccount(firstSelected.owner, firstSelected.account ?? "");
      }
      setSelectedIds([]);
      setFormSuccess(`Deleted ${selectedCount} transaction${selectedCount === 1 ? "" : "s"} successfully.`);
      setRefreshKey((key) => key + 1);
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Failed to delete selected transactions.");
    }
  }, [editingId, hasSelection, resetForm, selectedCount, selectedIds, setFilterOwnerAndAccount, transactionById]);

  const applyToSelected = useCallback(async () => {
    if (!hasSelection) {
      return;
    }
    const payload = createPayload();
    if (!payload) {
      return;
    }
    if (
      typeof window !== "undefined" &&
      !window.confirm(`Update ${selectedCount} selected transaction${selectedCount === 1 ? "" : "s"}?`)
    ) {
      return;
    }
    setFormError(null);
    setFormSuccess(null);
    setSubmitting(true);
    try {
      await Promise.all(selectedIds.map((id) => updateTransaction(id, payload)));
      if (editingId && selectedIds.includes(editingId)) {
        setEditingId(null);
      }
      setFilterOwnerAndAccount(payload.owner, payload.account);
      setSelectedIds([]);
      setFormSuccess(`Updated ${selectedCount} transaction${selectedCount === 1 ? "" : "s"} successfully.`);
      setRefreshKey((key) => key + 1);
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Failed to update selected transactions.");
    } finally {
      setSubmitting(false);
    }
  }, [createPayload, editingId, hasSelection, selectedCount, selectedIds, setFilterOwnerAndAccount]);

  const handleSubmit = useCallback(
    async (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      setFormError(null);
      setFormSuccess(null);
      const payload = createPayload();
      if (!payload) {
        return;
      }
      setSubmitting(true);
      try {
        if (editingId) {
          await updateTransaction(editingId, payload);
          setFormSuccess("Transaction updated successfully.");
          setEditingId(null);
        } else {
          await createTransaction(payload);
          setFormSuccess("Transaction created successfully.");
        }
        setFilterOwnerAndAccount(payload.owner, payload.account);
        resetForm();
        setRefreshKey((key) => key + 1);
      } catch (err) {
        setFormError(
          err instanceof Error
            ? err.message
            : editingId
              ? "Failed to update transaction."
              : "Failed to create transaction.",
        );
      } finally {
        setSubmitting(false);
      }
    },
    [createPayload, editingId, resetForm, setFilterOwnerAndAccount],
  );

  return {
    filters,
    form,
    transactions,
    paginatedTransactions,
    loading,
    error,
    accountOptions,
    newAccountOptions,
    submitting,
    formError,
    formSuccess,
    editingId,
    pageSize,
    pageSizeOptions: [10, 20, 50, 100],
    currentPage: totalTransactions === 0 ? 0 : clampedPage + 1,
    totalPages: totalTransactions === 0 ? 0 : totalPages,
    isFirstPage: clampedPage === 0,
    isLastPage: totalTransactions === 0 || clampedPage >= maxPageIndex,
    showingRangeLabel: buildShowingRangeLabel(totalTransactions, clampedPage, pageSize),
    selectedIds,
    selectedCount,
    hasSelection,
    allPageIds,
    isAllPageSelected,
    setFilterField,
    setFormField,
    handleOwnerChange,
    handleAccountChange,
    handleToggleSelect,
    handleToggleSelectAllOnPage,
    handlePageSizeChange,
    handlePreviousPage,
    handleNextPage,
    startEditing,
    cancelEditing,
    deleteOne,
    bulkDelete,
    applyToSelected,
    handleSubmit,
  };
}
