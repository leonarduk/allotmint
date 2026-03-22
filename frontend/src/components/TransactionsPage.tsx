import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useConfig } from "../ConfigContext";
import type { OwnerSummary } from "../types";
import { createOwnerDisplayLookup } from "../utils/owners";
import { TransactionsFilters } from "./transactions/TransactionsFilters";
import { TransactionsForm } from "./transactions/TransactionsForm";
import { TransactionsTable } from "./transactions/TransactionsTable";
import { useTransactionsController } from "./transactions/useTransactionsController";

type Props = {
  owners: OwnerSummary[];
};

export function TransactionsPage({ owners }: Props) {
  const { t } = useTranslation();
  const { baseCurrency } = useConfig();
  const ownerLookup = useMemo(() => createOwnerDisplayLookup(owners), [owners]);
  const controller = useTransactionsController(owners);

  return (
    <div>
      <TransactionsFilters
        owners={owners}
        ownerLookup={ownerLookup}
        owner={controller.filters.owner}
        account={controller.filters.account}
        start={controller.filters.start}
        end={controller.filters.end}
        accountOptions={controller.accountOptions}
        ownerLabel={t("owner.label")}
        startLabel={t("query.start")}
        endLabel={t("query.end")}
        onOwnerChange={controller.handleOwnerChange}
        onAccountChange={controller.handleAccountChange}
        onStartChange={(value) => controller.setFilterField("start", value)}
        onEndChange={(value) => controller.setFilterField("end", value)}
      />

      <TransactionsForm
        owners={owners}
        ownerLookup={ownerLookup}
        form={controller.form}
        newAccountOptions={controller.newAccountOptions}
        submitting={controller.submitting}
        editingId={controller.editingId}
        hasSelection={controller.hasSelection}
        selectedCount={controller.selectedCount}
        onFieldChange={controller.setFormField}
        onSubmit={controller.handleSubmit}
        onCancel={controller.cancelEditing}
        onApplyToSelected={controller.applyToSelected}
      />

      {controller.editingId && (
        <p style={{ color: "#ffd24d" }}>
          Editing existing transaction. Save or cancel to finish.
        </p>
      )}

      {controller.formError && <p style={{ color: "red" }}>{controller.formError}</p>}
      {controller.formSuccess && <p style={{ color: "limegreen" }}>{controller.formSuccess}</p>}
      {controller.error && <p style={{ color: "red" }}>{controller.error.message}</p>}

      {controller.loading ? (
        <p>{t("common.loading")}</p>
      ) : (
        <TransactionsTable
          transactions={controller.paginatedTransactions}
          ownerLookup={ownerLookup}
          baseCurrency={baseCurrency}
          pageSize={controller.pageSize}
          pageSizeOptions={controller.pageSizeOptions}
          showingRangeLabel={controller.showingRangeLabel}
          currentPage={controller.currentPage}
          totalPages={controller.totalPages}
          isFirstPage={controller.isFirstPage}
          isLastPage={controller.isLastPage}
          hasSelection={controller.hasSelection}
          selectedCount={controller.selectedCount}
          selectedIds={controller.selectedIds}
          allPageIds={controller.allPageIds}
          isAllPageSelected={controller.isAllPageSelected}
          onPageSizeChange={controller.handlePageSizeChange}
          onBulkDelete={controller.bulkDelete}
          onPreviousPage={controller.handlePreviousPage}
          onNextPage={controller.handleNextPage}
          onToggleSelectAllOnPage={controller.handleToggleSelectAllOnPage}
          onToggleSelect={controller.handleToggleSelect}
          onEdit={controller.startEditing}
          onDelete={controller.deleteOne}
        />
      )}
    </div>
  );
}
