import { useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { createManualHolding } from "../api";

type AmountMode = "unitsPrice" | "value";

type Props = {
  owner: string;
  accounts: string[];
  defaultAccount?: string;
  onAdded?: () => void;
  onCollapse?: () => void;
};

export function AddPositionForm({ owner, accounts, defaultAccount, onAdded, onCollapse }: Props) {
  const { t } = useTranslation();
  const [account, setAccount] = useState(defaultAccount ?? accounts[0] ?? "");
  const [ticker, setTicker] = useState("");
  const [mode, setMode] = useState<AmountMode>("unitsPrice");
  const [units, setUnits] = useState("");
  const [price, setPrice] = useState("");
  const [value, setValue] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSuccess(null);

    const trimmedTicker = ticker.trim().toUpperCase();
    if (!trimmedTicker) {
      setError(t("addPosition.errors.tickerRequired"));
      return;
    }
    if (!account) {
      setError(t("addPosition.errors.accountRequired"));
      return;
    }

    let payload: Parameters<typeof createManualHolding>[0];
    if (mode === "value") {
      const valueGbp = Number(value);
      if (!Number.isFinite(valueGbp) || valueGbp <= 0) {
        setError(t("addPosition.errors.positiveNumber"));
        return;
      }
      payload = { owner, account, ticker: trimmedTicker, value_gbp: valueGbp };
    } else {
      const unitsNum = Number(units);
      const priceNum = Number(price);
      if (units.trim() === "" || price.trim() === "") {
        setError(t("addPosition.errors.amountRequired"));
        return;
      }
      if (!Number.isFinite(unitsNum) || unitsNum <= 0 || !Number.isFinite(priceNum) || priceNum <= 0) {
        setError(t("addPosition.errors.positiveNumber"));
        return;
      }
      payload = { owner, account, ticker: trimmedTicker, units: unitsNum, price_gbp: priceNum };
    }

    setSubmitting(true);
    setError(null);
    try {
      await createManualHolding(payload);
      setSuccess(t("addPosition.success"));
      setTicker("");
      setUnits("");
      setPrice("");
      setValue("");
      onAdded?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("addPosition.errors.generic"));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form
      onSubmit={handleSubmit}
      aria-label={t("addPosition.title")}
      className="mb-6 rounded-lg border border-gray-800 bg-black/20 p-4"
    >
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-base font-semibold text-white">{t("addPosition.title")}</h3>
        {onCollapse && (
          <button
            type="button"
            onClick={onCollapse}
            aria-label={t("addPosition.collapse")}
            className="rounded border border-gray-700 px-2 py-0.5 text-sm text-white hover:border-gray-500 hover:bg-gray-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-400"
          >
            −
          </button>
        )}
      </div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <label className="text-sm text-gray-300">
          {t("addPosition.account")}
          <select
            value={account}
            onChange={(e) => setAccount(e.target.value)}
            className="mt-1 w-full rounded border border-gray-700 bg-gray-800 p-2 text-white"
          >
            {accounts.map((acct) => (
              <option key={acct} value={acct}>
                {acct}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm text-gray-300">
          {t("addPosition.ticker")}
          <input
            value={ticker}
            onChange={(e) => setTicker(e.target.value)}
            className="mt-1 w-full rounded border border-gray-700 bg-gray-800 p-2 text-white"
            placeholder="VWRL.L"
          />
        </label>
        <label className="text-sm text-gray-300">
          {t("addPosition.amountMode")}
          <select
            value={mode}
            onChange={(e) => setMode(e.target.value as AmountMode)}
            className="mt-1 w-full rounded border border-gray-700 bg-gray-800 p-2 text-white"
          >
            <option value="unitsPrice">{t("addPosition.unitsAndPrice")}</option>
            <option value="value">{t("addPosition.valueGbp")}</option>
          </select>
        </label>
        {mode === "unitsPrice" ? (
          <div className="grid grid-cols-2 gap-2">
            <label className="text-sm text-gray-300">
              {t("addPosition.units")}
              <input
                type="number"
                min="0"
                step="any"
                value={units}
                onChange={(e) => setUnits(e.target.value)}
                className="mt-1 w-full rounded border border-gray-700 bg-gray-800 p-2 text-white"
              />
            </label>
            <label className="text-sm text-gray-300">
              {t("addPosition.priceGbp")}
              <input
                type="number"
                min="0"
                step="any"
                value={price}
                onChange={(e) => setPrice(e.target.value)}
                className="mt-1 w-full rounded border border-gray-700 bg-gray-800 p-2 text-white"
              />
            </label>
          </div>
        ) : (
          <label className="text-sm text-gray-300">
            {t("addPosition.value")}
            <input
              type="number"
              min="0"
              step="any"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              className="mt-1 w-full rounded border border-gray-700 bg-gray-800 p-2 text-white"
            />
          </label>
        )}
      </div>
      <div className="mt-3 flex items-center gap-3">
        <button
          type="submit"
          disabled={submitting || !account}
          className="rounded bg-blue-600 px-3 py-1 text-white hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-60 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-400"
        >
          {submitting ? t("addPosition.submitting") : t("addPosition.submit")}
        </button>
        {error && (
          <span role="alert" className="text-sm text-red-500">
            {error}
          </span>
        )}
        {success && (
          <span role="status" className="text-sm text-green-500">
            {success}
          </span>
        )}
      </div>
    </form>
  );
}

export default AddPositionForm;
