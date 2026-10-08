import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { formatDateISO } from "@/lib/date";
import { transactionUnits } from "@/lib/transactionQuantity";
import tableStyles from "@/styles/table.module.css";
import type { Transaction } from "@/types";
import { getOwnerDisplayName } from "@/utils/owners";
import { useDemoReadOnly } from "@/hooks/useDemoReadOnly";
import type { MoneyFormatter } from "@/hooks/useReportingCurrency";
import {
  formatRealisedGain,
  formatTransactionAmount,
  getTransactionRowKey,
} from "./transactionTable";

interface TransactionsTableProps {
  transactions: Transaction[];
  /** Formats GBP amounts in the reporting currency (#9768). */
  format: MoneyFormatter;
  ownerLookup: Map<string, string>;
  pageSize: number;
  pageSizeOptions: number[];
  showingRangeLabel: string;
  currentPageDisplay: number;
  totalPagesDisplay: number;
  isFirstPage: boolean;
  isLastPage: boolean;
  hasSelection: boolean;
  selectedCount: number;
  selectedIds: string[];
  isAllPageSelected: boolean;
  allPageIds: string[];
  onPageSizeChange: (pageSize: number) => void;
  onBulkDelete: () => void;
  onPreviousPage: () => void;
  onNextPage: () => void;
  onToggleSelectAllOnPage: (checked: boolean) => void;
  onToggleSelect: (txId: string, checked: boolean) => void;
  onEdit: (transaction: Transaction) => void;
  onDelete: (transaction: Transaction) => void;
}

export function TransactionsTable({
  transactions,
  format,
  ownerLookup,
  pageSize,
  pageSizeOptions,
  showingRangeLabel,
  currentPageDisplay,
  totalPagesDisplay,
  isFirstPage,
  isLastPage,
  hasSelection,
  selectedCount,
  selectedIds,
  isAllPageSelected,
  allPageIds,
  onPageSizeChange,
  onBulkDelete,
  onPreviousPage,
  onNextPage,
  onToggleSelectAllOnPage,
  onToggleSelect,
  onEdit,
  onDelete,
}: TransactionsTableProps) {
  const { t } = useTranslation();
  const { demoReadOnly, reason } = useDemoReadOnly();
  return (
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
          {t("transactionsTable.rowsPerPage")}
          <select
            value={pageSize}
            onChange={(event) => onPageSizeChange(Number(event.target.value))}
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
          onClick={onBulkDelete}
          disabled={!hasSelection || demoReadOnly}
          title={reason()}
        >
          {t("transactionsTable.deleteSelected")}
          {hasSelection ? ` (${selectedCount})` : ""}
        </button>
        <div
          className="flex-wrap-row"
          style={{ alignItems: "center", gap: "0.5rem" }}
        >
          <span>{showingRangeLabel}</span>
          <button type="button" onClick={onPreviousPage} disabled={isFirstPage}>
            {t("transactionsTable.previous")}
          </button>
          <span>
            {t("transactionsTable.pageOf", {
              current: currentPageDisplay,
              total: totalPagesDisplay,
            })}
          </span>
          <button type="button" onClick={onNextPage} disabled={isLastPage}>
            {t("transactionsTable.next")}
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
                onChange={(event) => onToggleSelectAllOnPage(event.target.checked)}
                aria-label={t("transactionsTable.selectAll")}
              />
            </th>
            <th className={tableStyles.cell}>{t("transactionsTable.date")}</th>
            <th className={tableStyles.cell}>{t("transactionsTable.owner")}</th>
            <th className={tableStyles.cell}>{t("transactionsTable.account")}</th>
            <th className={tableStyles.cell}>{t("transactionsTable.instrument")}</th>
            <th className={tableStyles.cell}>{t("transactionsTable.instrumentName")}</th>
            <th className={tableStyles.cell}>{t("transactionsTable.type")}</th>
            <th className={`${tableStyles.cell} ${tableStyles.right}`}>{t("transactionsTable.amount")}</th>
            <th className={`${tableStyles.cell} ${tableStyles.right}`}>{t("transactionsTable.shares")}</th>
            <th className={`${tableStyles.cell} ${tableStyles.right}`}>{t("transactionsTable.gainLoss")}</th>
            <th className={tableStyles.cell}>{t("transactionsTable.actions")}</th>
          </tr>
        </thead>
        <tbody>
          {transactions.length === 0 ? (
            <tr>
              <td className={tableStyles.cell} colSpan={11} style={{ textAlign: "center" }}>
                {t("transactionsTable.empty")}
              </td>
            </tr>
          ) : (
            transactions.map((transaction, index) => {
              const key = getTransactionRowKey(transaction, index);
              const gain = formatRealisedGain(transaction, format);

              return (
                <tr key={key}>
                  <td className={tableStyles.cell}>
                    <input
                      type="checkbox"
                      disabled={!transaction.id}
                      checked={transaction.id ? selectedIds.includes(transaction.id) : false}
                      onChange={(event) =>
                        transaction.id && onToggleSelect(transaction.id, event.target.checked)
                      }
                      aria-label={t("transactionsTable.selectTransaction", {
                        id: transaction.id ?? key,
                      })}
                    />
                  </td>
                  <td className={tableStyles.cell}>
                    {transaction.date ? formatDateISO(new Date(transaction.date)) : ""}
                  </td>
                  <td className={tableStyles.cell}>
                    {getOwnerDisplayName(
                      ownerLookup,
                      transaction.owner ?? null,
                      transaction.owner ?? "—",
                    )}
                  </td>
                  <td className={tableStyles.cell}>{transaction.account}</td>
                  <td className={tableStyles.cell}>
                    {/* security_ref is an unresolved Portfolio Performance reference,
                        not a ticker, so only a real ticker links to research. */}
                    {transaction.ticker ? (
                      <Link to={`/research/${encodeURIComponent(transaction.ticker)}`}>
                        {transaction.ticker}
                      </Link>
                    ) : (
                      transaction.security_ref || ""
                    )}
                  </td>
                  <td className={tableStyles.cell}>{transaction.instrument_name || ""}</td>
                  <td className={tableStyles.cell}>{transaction.type || transaction.kind}</td>
                  <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                    {formatTransactionAmount(transaction, format)}
                  </td>
                  <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                    {transactionUnits(transaction) ?? ""}
                  </td>
                  <td
                    className={`${tableStyles.cell} ${tableStyles.right} ${gain.className}`}
                    title={gain.title}
                  >
                    {gain.text}
                  </td>
                  <td className={tableStyles.cell}>
                    <div style={{ display: "flex", gap: "0.5rem" }}>
                      <button
                        type="button"
                        onClick={() => onEdit(transaction)}
                        disabled={!transaction.id || demoReadOnly}
                        title={reason()}
                      >
                        {t("transactionsTable.edit")}
                      </button>
                      <button
                        type="button"
                        onClick={() => onDelete(transaction)}
                        disabled={!transaction.id || demoReadOnly}
                        title={reason()}
                      >
                        {t("transactionsTable.delete")}
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
  );
}
