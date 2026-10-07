import { useEffect, useMemo, useState } from "react";
import type { ChangeEvent, FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { createTransaction, getOwners } from "../api";
import { useDemoReadOnly } from "../hooks/useDemoReadOnly";
import { localDateISO } from "../lib/date";
import { money } from "../lib/money";
import type { InstrumentPosition, OwnerSummary } from "../types";
import {
  buildTransactionPayload,
  EMPTY_TRANSACTION_FORM_VALUES,
  type TradeType,
  type TransactionFormValues,
} from "./transactions/transactionForm";
import {
  buildTradeAccounts,
  defaultPriceUnit,
  isOversell,
  toPriceGbp,
  tradeAccountValue,
  tradeTotalGbp,
  type PriceUnit,
  type TradeAccount,
} from "./transactions/recordTrade";

type Props = {
  ticker: string;
  side: TradeType;
  positions: InstrumentPosition[];
  /** The instrument's quote currency; GBX/GBp defaults price entry to pence. */
  quoteCurrency?: string | null;
  onSaved: (side: TradeType) => void;
  onCancel: () => void;
};

const column = { display: "flex", flexDirection: "column" } as const;

/** Owners/accounts from /owners merged with the accounts already holding it. */
function useTradeAccounts(positions: InstrumentPosition[]) {
  const { t } = useTranslation();
  const [owners, setOwners] = useState<OwnerSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    getOwners()
      .then((data) => {
        if (active) setOwners(data);
      })
      .catch((err: unknown) => {
        if (active)
          setError(err instanceof Error ? err.message : t("recordTrade.ownersFailed"));
      });
    return () => {
      active = false;
    };
  }, [t]);
  const accounts = useMemo(() => buildTradeAccounts(positions, owners), [positions, owners]);
  return { accounts, error };
}

/** Form state, derived trade figures and the submit handler. */
function useRecordTrade({ ticker, side, positions, quoteCurrency, onSaved }: Omit<Props, "onCancel">) {
  const { t } = useTranslation();
  const { accounts, error: ownersError } = useTradeAccounts(positions);
  const [values, setValues] = useState<TransactionFormValues>(() => ({
    ...EMPTY_TRANSACTION_FORM_VALUES,
    type: side,
    ticker: ticker.toUpperCase(),
    date: localDateISO(),
  }));
  const [unit, setUnit] = useState<PriceUnit>(() => defaultPriceUnit(quoteCurrency));
  const [accountValue, setAccountValue] = useState("");
  const [confirmOversell, setConfirmOversell] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selected: TradeAccount | undefined =
    accounts.find((a) => tradeAccountValue(a) === accountValue) ?? accounts[0];
  const tradeSide: TradeType = values.type === "SELL" ? "SELL" : "BUY";
  const units = Number(values.units);
  const priceGbp = toPriceGbp(values.price, unit);
  const total = tradeTotalGbp(tradeSide, units, priceGbp, Number(values.fees));
  const oversell = isOversell(tradeSide, units, selected);

  const onField =
    (field: keyof TransactionFormValues) =>
    (e: ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
      setValues((prev) => ({ ...prev, [field]: e.target.value }));

  const submit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!selected) {
      setError(t("recordTrade.noAccount"));
      return;
    }
    const priced = { ...values, price: Number.isFinite(priceGbp) ? String(priceGbp) : "" };
    const built = buildTransactionPayload(priced, selected.owner, selected.account);
    if (built.error !== null) {
      setError(built.error);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await createTransaction(built.payload);
      onSaved(tradeSide);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("recordTrade.saveFailed"));
    } finally {
      setSaving(false);
    }
  };

  return {
    accounts, ownersError, values, unit, setUnit, setAccountValue, confirmOversell,
    setConfirmOversell, saving, error, selected, tradeSide, priceGbp, total, oversell,
    onField, submit,
  };
}

/**
 * Record a BUY or SELL of one instrument via POST /transactions, from the
 * Research page (#9991). Price can be typed in pounds or pence; the total
 * is shown in GBP so a 100x pence/pounds slip is visible before saving.
 */
export function RecordTradeForm(props: Props) {
  const { ticker, onCancel } = props;
  const { t } = useTranslation();
  const { demoReadOnly, reason } = useDemoReadOnly();
  const {
    accounts, ownersError, values, unit, setUnit, setAccountValue, confirmOversell,
    setConfirmOversell, saving, error, selected, tradeSide, priceGbp, total, oversell,
    onField, submit,
  } = useRecordTrade(props);
  const blocked = saving || demoReadOnly || !selected || (oversell && !confirmOversell);
  return (
    <form
      aria-label={t("recordTrade.title", { ticker })}
      onSubmit={(e) => void submit(e)}
      style={{ display: "flex", flexWrap: "wrap", gap: "0.75rem", alignItems: "flex-end", marginBottom: "1rem" }}
    >
      <TradeCoreFields
        values={values}
        onField={onField}
        accounts={accounts}
        accountValue={selected ? tradeAccountValue(selected) : ""}
        onAccountChange={(v) => {
          setAccountValue(v);
          setConfirmOversell(false);
        }}
      />
      <TradePriceFields values={values} onField={onField} unit={unit} onUnitChange={setUnit} />
      <div style={column}>
        <strong>{t("recordTrade.total")}</strong>
        <output aria-label={t("recordTrade.total")}>{money(total, "GBP")}</output>
        {unit === "GBX" && Number.isFinite(priceGbp) && (
          <small>{t("recordTrade.priceInPounds", { price: money(priceGbp, "GBP") })}</small>
        )}
      </div>
      {oversell && selected && (
        <OversellWarning
          units={values.units}
          held={selected.heldUnits}
          confirmed={confirmOversell}
          onConfirm={setConfirmOversell}
        />
      )}
      {(error || ownersError) && (
        <div role="alert" style={{ flexBasis: "100%", color: "red" }}>
          {error ?? ownersError}
        </div>
      )}
      <button type="submit" disabled={blocked} title={reason()}>
        {saving ? t("transactionEditor.saving") : t("recordTrade.save", { side: t(tradeSide === "SELL" ? "recordTrade.sell" : "recordTrade.buy") })}
      </button>
      <button type="button" onClick={onCancel} disabled={saving}>
        {t("common.cancel")}
      </button>
    </form>
  );
}

type OversellWarningProps = {
  units: string;
  held: number;
  confirmed: boolean;
  onConfirm: (confirmed: boolean) => void;
};

function OversellWarning({ units, held, confirmed, onConfirm }: OversellWarningProps) {
  const { t } = useTranslation();
  return (
    <div role="alert" style={{ flexBasis: "100%", color: "#c47f00" }}>
      {t("recordTrade.oversell", { units, held })}{" "}
      <label>
        <input type="checkbox" checked={confirmed} onChange={(e) => onConfirm(e.target.checked)} />{" "}
        {t("recordTrade.oversellConfirm")}
      </label>
    </div>
  );
}

type FieldChange = (
  field: keyof TransactionFormValues,
) => (e: ChangeEvent<HTMLInputElement | HTMLSelectElement>) => void;

type CoreFieldsProps = {
  values: TransactionFormValues;
  onField: FieldChange;
  accounts: TradeAccount[];
  accountValue: string;
  onAccountChange: (value: string) => void;
};

function TradeCoreFields({ values, onField, accounts, accountValue, onAccountChange }: CoreFieldsProps) {
  const { t } = useTranslation();
  return (
    <>
      <label style={column}>
        {t("transactionEditor.type")}
        <select value={values.type} onChange={onField("type")}>
          <option value="BUY">{t("transactionEditor.buy")}</option>
          <option value="SELL">{t("transactionEditor.sell")}</option>
        </select>
      </label>
      <label style={column}>
        {t("recordTrade.account")}
        <select value={accountValue} onChange={(e) => onAccountChange(e.target.value)}>
          {accounts.map((a) => (
            <option key={tradeAccountValue(a)} value={tradeAccountValue(a)}>
              {a.heldUnits > 0
                ? t("recordTrade.accountHeld", { owner: a.owner, account: a.account.toUpperCase(), units: a.heldUnits })
                : `${a.owner} / ${a.account.toUpperCase()}`}
            </option>
          ))}
        </select>
      </label>
      <label style={column}>
        {t("transactionEditor.date")}
        <input type="date" value={values.date} onChange={onField("date")} required />
      </label>
      <label style={column}>
        {t("transactionEditor.units")}
        <input type="number" step="any" min="0" value={values.units} onChange={onField("units")} required />
      </label>
    </>
  );
}

type PriceFieldsProps = {
  values: TransactionFormValues;
  onField: FieldChange;
  unit: PriceUnit;
  onUnitChange: (unit: PriceUnit) => void;
};

function TradePriceFields({ values, onField, unit, onUnitChange }: PriceFieldsProps) {
  const { t } = useTranslation();
  return (
    <>
      <label style={column}>
        {unit === "GBX" ? t("recordTrade.pricePence") : t("recordTrade.pricePounds")}
        <input type="number" step="any" min="0" value={values.price} onChange={onField("price")} required />
      </label>
      <label style={column}>
        {t("recordTrade.priceUnit")}
        <select value={unit} onChange={(e) => onUnitChange(e.target.value === "GBX" ? "GBX" : "GBP")}>
          <option value="GBP">{t("recordTrade.unitGbp")}</option>
          <option value="GBX">{t("recordTrade.unitGbx")}</option>
        </select>
      </label>
      <label style={column}>
        {t("recordTrade.feesGbp")}
        <input type="number" step="0.01" min="0" value={values.fees} onChange={onField("fees")} />
      </label>
      <label style={{ ...column, minWidth: "180px" }}>
        {t("transactionEditor.reason")}
        <input type="text" value={values.reason} onChange={onField("reason")} required />
      </label>
      <label style={{ ...column, minWidth: "180px" }}>
        {t("transactionEditor.comments")}
        <input
          type="text"
          value={values.comments}
          onChange={onField("comments")}
          placeholder={t("transactionEditor.optional")}
        />
      </label>
    </>
  );
}
