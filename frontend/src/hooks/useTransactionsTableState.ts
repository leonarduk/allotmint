import { useEffect, useMemo, useState, useCallback } from "react";
import type { Transaction } from "@/types";

export function useTransactionsTableState(transactions: Transaction[] | undefined) {
  const [pageSize, setPageSize] = useState(20);
  const [currentPage, setCurrentPage] = useState(0);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);

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
    if (!transactions || transactions.length === 0) {
      setSelectedIds((prev) => (prev.length > 0 ? [] : prev));
      return;
    }

    const validIds = new Set(
      transactions.map((tx) => tx.id).filter((id): id is string => Boolean(id)),
    );
    setSelectedIds((prev) => prev.filter((id) => validIds.has(id)));
  }, [transactions]);

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

  const allPageIds = useMemo(
    () => paginatedTransactions.map((tx) => tx.id).filter((id): id is string => Boolean(id)),
    [paginatedTransactions],
  );

  const selectedCount = selectedIds.length;
  const hasSelection = selectedCount > 0;
  const isAllPageSelected =
    allPageIds.length > 0 && allPageIds.every((id) => selectedIds.includes(id));

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

  const handlePreviousPage = useCallback(() => {
    setCurrentPage((page) => Math.max(page - 1, 0));
  }, []);

  const handleNextPage = useCallback(() => {
    setCurrentPage((page) => page + 1);
  }, []);

  const resetToFirstPage = useCallback(() => {
    setCurrentPage(0);
  }, []);

  return {
    pageSize,
    setPageSize,
    currentPage,
    resetToFirstPage,
    selectedIds,
    setSelectedIds,
    transactionById,
    paginatedTransactions,
    allPageIds,
    selectedCount,
    hasSelection,
    isAllPageSelected,
    isFirstPage,
    isLastPage,
    showingRangeLabel,
    currentPageDisplay,
    totalPagesDisplay,
    handleToggleSelect,
    handleToggleSelectAllOnPage,
    handlePreviousPage,
    handleNextPage,
  };
}
