import { Selector } from "../Selector";
import type { OwnerSummary } from "../../types";
import type { TransactionFormState } from "./helpers";
import { getOwnerDisplayName } from "../../utils/owners";

type Props = {
  owners: OwnerSummary[];
  ownerLookup: Map<string, string>;
  form: TransactionFormState;
  newAccountOptions: string[];
  submitting: boolean;
  editingId: string | null;
  hasSelection: boolean;
  selectedCount: number;
  onFieldChange: (key: keyof TransactionFormState, value: string) => void;
  onSubmit: (event: React.FormEvent<HTMLFormElement>) => void;
  onCancel: () => void;
  onApplyToSelected: () => void;
};

export function TransactionsForm({
  owners,
  ownerLookup,
  form,
  newAccountOptions,
  submitting,
  editingId,
  hasSelection,
  selectedCount,
  onFieldChange,
  onSubmit,
  onCancel,
  onApplyToSelected,
}: Props) {
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
        value={form.owner}
        onChange={(event) => onFieldChange("owner", event.target.value)}
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
        value={form.account}
        onChange={(event) => onFieldChange("account", event.target.value)}
        options={[
          { value: "", label: form.owner ? "Select" : "Select owner first" },
          ...newAccountOptions.map((value) => ({ value, label: value })),
        ]}
      />
      <label style={{ display: "flex", flexDirection: "column" }}>
        Date
        <input type="date" value={form.date} onChange={(event) => onFieldChange("date", event.target.value)} required />
      </label>
      <label style={{ display: "flex", flexDirection: "column" }}>
        Ticker
        <input
          type="text"
          value={form.ticker}
          onChange={(event) => onFieldChange("ticker", event.target.value.toUpperCase())}
          placeholder="e.g. VUSA"
          required
        />
      </label>
      <label style={{ display: "flex", flexDirection: "column" }}>
        Price (GBP)
        <input type="number" step="0.01" min="0" value={form.price} onChange={(event) => onFieldChange("price", event.target.value)} required />
      </label>
      <label style={{ display: "flex", flexDirection: "column" }}>
        Units
        <input type="number" step="0.0001" min="0" value={form.units} onChange={(event) => onFieldChange("units", event.target.value)} required />
      </label>
      <label style={{ display: "flex", flexDirection: "column" }}>
        Fees (GBP)
        <input type="number" step="0.01" min="0" value={form.fees} onChange={(event) => onFieldChange("fees", event.target.value)} />
      </label>
      <label style={{ display: "flex", flexDirection: "column", minWidth: "180px" }}>
        Reason
        <input type="text" value={form.reason} onChange={(event) => onFieldChange("reason", event.target.value)} required />
      </label>
      <label style={{ display: "flex", flexDirection: "column", minWidth: "180px" }}>
        Comments
        <input
          type="text"
          value={form.comments}
          onChange={(event) => onFieldChange("comments", event.target.value)}
          placeholder="Optional"
        />
      </label>
      <button type="submit" disabled={submitting} style={{ height: "2.3rem" }}>
        {submitting ? (editingId ? "Updating..." : "Saving...") : editingId ? "Update transaction" : "Add transaction"}
      </button>
      {editingId && (
        <button type="button" onClick={onCancel} disabled={submitting} style={{ height: "2.3rem" }}>
          Cancel
        </button>
      )}
      <button type="button" onClick={onApplyToSelected} disabled={!hasSelection || submitting} style={{ height: "2.3rem" }}>
        Apply to selected{hasSelection ? ` (${selectedCount})` : ""}
      </button>
    </form>
  );
}
