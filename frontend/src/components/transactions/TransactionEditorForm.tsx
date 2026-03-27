import type { ChangeEventHandler, FormEventHandler } from "react";
import type { TransactionFormValues } from "./transactionForm";

interface TransactionEditorFormProps {
  values: TransactionFormValues;
  activeOwner: string;
  activeAccount: string;
  editingId: string | null;
  hasSelection: boolean;
  selectedCount: number;
  submitting: boolean;
  onSubmit: FormEventHandler<HTMLFormElement>;
  onFieldChange: <K extends keyof TransactionFormValues>(
    field: K,
  ) => ChangeEventHandler<HTMLInputElement | HTMLSelectElement>;
  onCancelEdit: () => void;
  onApplyToSelected: () => void;
}

export function TransactionEditorForm({
  values,
  activeOwner,
  activeAccount,
  editingId,
  hasSelection,
  selectedCount,
  submitting,
  onSubmit,
  onFieldChange,
  onCancelEdit,
  onApplyToSelected,
}: TransactionEditorFormProps) {
  const ownerAndAccountSelected = Boolean(activeOwner && activeAccount);

  return (
    <form
      onSubmit={onSubmit}
      style={{
        display: "flex",
        flexWrap: "wrap",
        gap: "0.75rem",
        alignItems: "flex-end",
        marginBottom: "1rem",
      }}
    >
      <div style={{ display: "flex", flexDirection: "column", gap: "0.2rem" }}>
        <strong>Applies to</strong>
        {ownerAndAccountSelected ? (
          <span>
            {activeOwner} / {activeAccount}
          </span>
        ) : (
          <span style={{ opacity: 0.8 }}>Select an owner and account in filters above.</span>
        )}
      </div>
      <label style={{ display: "flex", flexDirection: "column" }}>
        Date
        <input type="date" value={values.date} onChange={onFieldChange("date")} required />
      </label>
      <label style={{ display: "flex", flexDirection: "column" }}>
        Ticker
        <input
          type="text"
          value={values.ticker}
          onChange={onFieldChange("ticker")}
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
          value={values.price}
          onChange={onFieldChange("price")}
          required
        />
      </label>
      <label style={{ display: "flex", flexDirection: "column" }}>
        Units
        <input
          type="number"
          step="0.0001"
          min="0"
          value={values.units}
          onChange={onFieldChange("units")}
          required
        />
      </label>
      <label style={{ display: "flex", flexDirection: "column" }}>
        Fees (GBP)
        <input
          type="number"
          step="0.01"
          min="0"
          value={values.fees}
          onChange={onFieldChange("fees")}
        />
      </label>
      <label style={{ display: "flex", flexDirection: "column", minWidth: "180px" }}>
        Reason
        <input type="text" value={values.reason} onChange={onFieldChange("reason")} required />
      </label>
      <label style={{ display: "flex", flexDirection: "column", minWidth: "180px" }}>
        Comments
        <input
          type="text"
          value={values.comments}
          onChange={onFieldChange("comments")}
          placeholder="Optional"
        />
      </label>
      <button
        type="submit"
        disabled={submitting || !ownerAndAccountSelected}
        style={{ height: "2.3rem" }}
      >
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
          onClick={onCancelEdit}
          disabled={submitting}
          style={{ height: "2.3rem" }}
        >
          Cancel
        </button>
      )}
      <button
        type="button"
        onClick={onApplyToSelected}
        disabled={!hasSelection || submitting}
        style={{ height: "2.3rem" }}
      >
        Apply to selected{hasSelection ? ` (${selectedCount})` : ""}
      </button>
    </form>
  );
}
