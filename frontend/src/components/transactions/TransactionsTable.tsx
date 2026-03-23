import { formatDateISO } from "@/lib/date";
import tableStyles from "@/styles/table.module.css";
import type { Transaction } from "@/types";
import { getOwnerDisplayName } from "@/utils/owners";
import {
  formatTransactionAmount,
  getTransactionRowKey,
} from "./transactionTable";

interface TransactionsTableProps {
  transactions: Transaction[];
  baseCurrency: string;
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
  baseCurrency,
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
          Rows per page:
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
        <button type="button" onClick={onBulkDelete} disabled={!hasSelection}>
          Delete selected{hasSelection ? ` (${selectedCount})` : ""}
        </button>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <span>{showingRangeLabel}</span>
          <button type="button" onClick={onPreviousPage} disabled={isFirstPage}>
            Previous
          </button>
          <span>
            Page {currentPageDisplay} of {totalPagesDisplay}
          </span>
          <button type="button" onClick={onNextPage} disabled={isLastPage}>
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
                onChange={(event) => onToggleSelectAllOnPage(event.target.checked)}
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
          {transactions.length === 0 ? (
            <tr>
              <td className={tableStyles.cell} colSpan={10} style={{ textAlign: "center" }}>
                No transactions found.
              </td>
            </tr>
          ) : (
            transactions.map((transaction, index) => {
              const key = getTransactionRowKey(transaction, index);

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
                      aria-label={`Select transaction ${transaction.id ?? key}`}
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
                    {transaction.ticker || transaction.security_ref || ""}
                  </td>
                  <td className={tableStyles.cell}>{transaction.instrument_name || ""}</td>
                  <td className={tableStyles.cell}>{transaction.type || transaction.kind}</td>
                  <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                    {formatTransactionAmount(transaction, baseCurrency)}
                  </td>
                  <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                    {transaction.shares ?? transaction.units ?? ""}
                  </td>
                  <td className={tableStyles.cell}>
                    <div style={{ display: "flex", gap: "0.5rem" }}>
                      <button type="button" onClick={() => onEdit(transaction)} disabled={!transaction.id}>
                        Edit
                      </button>
                      <button
                        type="button"
                        onClick={() => onDelete(transaction)}
                        disabled={!transaction.id}
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
  );
}
