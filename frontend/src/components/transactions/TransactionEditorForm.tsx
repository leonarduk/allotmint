import type { ChangeEventHandler, FormEventHandler } from "react";
import type { OwnerSummary } from "@/types";
import { Selector } from "@/components/Selector";
import { getOwnerDisplayName } from "@/utils/owners";
import type { TransactionFormValues } from "./transactionForm";

interface TransactionEditorFormProps {
  values: TransactionFormValues;
  owners: OwnerSummary[];
  ownerLookup: Map<string, string>;
  accountOptions: string[];
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
  owners,
  ownerLookup,
  accountOptions,
  editingId,
  hasSelection,
  selectedCount,
  submitting,
  onSubmit,
  onFieldChange,
  onCancelEdit,
  onApplyToSelected,
}: TransactionEditorFormProps) {
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
      <Selector
        label="Owner"
        value={values.owner}
        onChange={onFieldChange("owner")}
        options={[
          { value: "", label: "Select" },
          ...owners.map((entry) => ({
            value: entry.owner,
            label: getOwnerDisplayName(ownerLookup, entry.owner, entry.owner),
          })),
        ]}
      />
      <Selector
        label="Account"
        value={values.account}
        onChange={onFieldChange("account")}
        options={[
          { value: "", label: values.owner ? "Select" : "Select owner first" },
          ...accountOptions.map((option) => ({ value: option, label: option })),
        ]}
      />
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
