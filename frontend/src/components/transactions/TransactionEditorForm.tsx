import { useTranslation } from "react-i18next";
import type { ChangeEventHandler, FormEventHandler } from "react";
import { isTradeType, type TransactionFormValues } from "./transactionForm";
import { useDemoReadOnly } from "../../hooks/useDemoReadOnly";

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
  const { t } = useTranslation();
  const { demoReadOnly, reason } = useDemoReadOnly();
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
        <strong>{t("transactionEditor.appliesTo")}</strong>
        {ownerAndAccountSelected ? (
          <span>
            {activeOwner} / {activeAccount}
          </span>
        ) : (
          <span style={{ opacity: 0.8 }}>{t("transactionEditor.selectOwnerAccount")}</span>
        )}
      </div>
      <label style={{ display: "flex", flexDirection: "column" }}>
        {t("transactionEditor.type")}
        <select value={values.type} onChange={onFieldChange("type")}>
          <option value="BUY">{t("transactionEditor.buy")}</option>
          <option value="SELL">{t("transactionEditor.sell")}</option>
          {!isTradeType(values.type) && (
            <option value={values.type}>{t("transactionEditor.unchangedType", {
                type: values.type || t("transactionEditor.untyped"),
              })}</option>
          )}
        </select>
      </label>
      <label style={{ display: "flex", flexDirection: "column" }}>
        {t("transactionEditor.date")}
        <input type="date" value={values.date} onChange={onFieldChange("date")} required />
      </label>
      <label style={{ display: "flex", flexDirection: "column" }}>
        {t("transactionEditor.ticker")}
        <input
          type="text"
          value={values.ticker}
          onChange={onFieldChange("ticker")}
          placeholder={t("transactionEditor.tickerPlaceholder")}
          required
        />
      </label>
      <label style={{ display: "flex", flexDirection: "column" }}>
        {t("transactionEditor.price")}
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
        {t("transactionEditor.units")}
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
        {t("transactionEditor.fees")}
        <input
          type="number"
          step="0.01"
          min="0"
          value={values.fees}
          onChange={onFieldChange("fees")}
        />
      </label>
      <label style={{ display: "flex", flexDirection: "column", minWidth: "180px" }}>
        {t("transactionEditor.reason")}
        <input type="text" value={values.reason} onChange={onFieldChange("reason")} required />
      </label>
      <label style={{ display: "flex", flexDirection: "column", minWidth: "180px" }}>
        {t("transactionEditor.comments")}
        <input
          type="text"
          value={values.comments}
          onChange={onFieldChange("comments")}
          placeholder={t("transactionEditor.optional")}
        />
      </label>
      <button
        type="submit"
        disabled={submitting || !ownerAndAccountSelected || demoReadOnly}
        title={reason()}
        style={{ height: "2.3rem" }}
      >
        {submitting
          ? editingId
            ? t("transactionEditor.updating")
            : t("transactionEditor.saving")
          : editingId
            ? t("transactionEditor.update")
            : t("transactionEditor.add")}
      </button>
      {editingId && (
        <button
          type="button"
          onClick={onCancelEdit}
          disabled={submitting}
          style={{ height: "2.3rem" }}
        >
          {t("common.cancel")}
        </button>
      )}
      <button
        type="button"
        onClick={onApplyToSelected}
        disabled={!hasSelection || submitting || demoReadOnly}
        title={reason()}
        style={{ height: "2.3rem" }}
      >
        {t("transactionEditor.applyToSelected")}
        {hasSelection ? ` (${selectedCount})` : ""}
      </button>
    </form>
  );
}
