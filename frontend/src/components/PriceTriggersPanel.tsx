import { useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";
import {
  createPriceTrigger,
  deletePriceTrigger,
  getPriceTriggers,
  updatePriceTrigger,
} from "../api";
import { triggersForTicker } from "../hooks/useInstrumentAlertCount";
import type {
  PriceTrigger,
  PriceTriggerCondition,
  PriceTriggerMode,
} from "../api";

interface Props {
  /** Resolved alert identity the triggers belong to. */
  identity: string;
  /** True when the identity is unknown/forbidden or the deployment is read-only. */
  disabled: boolean;
  disabledReason?: string;
  /**
   * Scope the panel to one ticker (e.g. on the research page): only that
   * ticker's triggers are listed and new triggers are created for it, so the
   * ticker field and column are hidden.
   */
  ticker?: string;
  /** Latest GBP price for the scoped ticker, shown as a hint beside the form. */
  latestPrice?: number | null;
  /** Called with the listed triggers each time they are (re)loaded. */
  onTriggersLoaded?: (visible: PriceTrigger[]) => void;
}

interface FormState {
  ticker: string;
  condition: PriceTriggerCondition;
  price: string;
  mode: PriceTriggerMode;
  note: string;
}

const EMPTY_FORM: FormState = {
  ticker: "",
  condition: "above",
  price: "",
  mode: "once",
  note: "",
};

function emptyForm(ticker?: string): FormState {
  return { ...EMPTY_FORM, ticker: ticker ?? "" };
}

function errorMessage(err: unknown, fallback: string): string {
  const detail = (err as { message?: string })?.message;
  return detail || fallback;
}

export default function PriceTriggersPanel({
  identity,
  disabled,
  disabledReason,
  ticker,
  latestPrice,
  onTriggersLoaded,
}: Props) {
  const { t } = useTranslation();
  const scoped = !!ticker;
  const [triggers, setTriggers] = useState<PriceTrigger[]>([]);
  const [form, setForm] = useState<FormState>(() => emptyForm(ticker));
  const [editingId, setEditingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // Held in a ref so an inline callback from the parent doesn't change
  // `reload`'s identity and re-fetch on every render.
  const onLoadedRef = useRef(onTriggersLoaded);
  onLoadedRef.current = onTriggersLoaded;

  const reload = useCallback(async () => {
    if (!identity) {
      setTriggers([]);
      return;
    }
    try {
      const rows = await getPriceTriggers(identity);
      setTriggers(rows);
      onLoadedRef.current?.(ticker ? triggersForTicker(rows, ticker) : rows);
      setError(null);
    } catch (err) {
      setError(errorMessage(err, t("alertSettings.triggers.loadError")));
    }
  }, [identity, ticker, t]);

  useEffect(() => {
    void reload();
  }, [reload]);

  // Navigating between instruments re-uses this component; drop any
  // half-finished edit so it can't be saved against the wrong ticker.
  useEffect(() => {
    setEditingId(null);
    setError(null);
    setForm(emptyForm(ticker));
  }, [ticker]);

  const visible = ticker ? triggersForTicker(triggers, ticker) : triggers;

  const priceValue = Number(form.price);
  const formValid =
    form.ticker.trim() !== "" && Number.isFinite(priceValue) && priceValue > 0;

  async function run(action: () => Promise<unknown>, failure: string) {
    setBusy(true);
    try {
      await action();
      setError(null);
      await reload();
    } catch (err) {
      setError(errorMessage(err, failure));
    } finally {
      setBusy(false);
    }
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!formValid || disabled) return;
    const body = {
      ticker: form.ticker.trim(),
      condition: form.condition,
      price: priceValue,
      mode: form.mode,
      note: form.note.trim() || null,
    };
    await run(
      () =>
        editingId
          ? updatePriceTrigger(identity, editingId, body)
          : createPriceTrigger(identity, body),
      t("alertSettings.triggers.saveError"),
    );
    setForm(emptyForm(ticker));
    setEditingId(null);
  }

  function edit(trigger: PriceTrigger) {
    setEditingId(trigger.id);
    setForm({
      ticker: trigger.ticker,
      condition: trigger.condition,
      price: String(trigger.price),
      mode: trigger.mode,
      note: trigger.note ?? "",
    });
  }

  function cancelEdit() {
    setEditingId(null);
    setForm(emptyForm(ticker));
  }

  return (
    <section
      style={{ marginTop: scoped ? 0 : "2rem" }}
      aria-labelledby="price-triggers-title"
    >
      <h2 id="price-triggers-title">
        {scoped ? t("alertSettings.triggers.instrumentTitle") : t("alertSettings.triggers.title")}
      </h2>
      <p>
        {scoped
          ? t("alertSettings.triggers.instrumentDescription", { ticker })
          : t("alertSettings.triggers.description")}
      </p>

      <form onSubmit={submit} style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
        {!scoped && (
          <input
            aria-label={t("alertSettings.triggers.ticker")}
            placeholder={t("alertSettings.triggers.ticker")}
            value={form.ticker}
            onChange={(e) => setForm({ ...form, ticker: e.target.value })}
            disabled={disabled}
            style={{ width: "7rem" }}
          />
        )}
        <select
          aria-label={t("alertSettings.triggers.condition")}
          value={form.condition}
          onChange={(e) =>
            setForm({ ...form, condition: e.target.value as PriceTriggerCondition })
          }
          disabled={disabled}
        >
          <option value="above">{t("alertSettings.triggers.above")}</option>
          <option value="below">{t("alertSettings.triggers.below")}</option>
        </select>
        <input
          type="number"
          min="0"
          step="any"
          aria-label={t("alertSettings.triggers.price")}
          placeholder={t("alertSettings.triggers.price")}
          value={form.price}
          onChange={(e) => setForm({ ...form, price: e.target.value })}
          disabled={disabled}
          style={{ width: "6rem" }}
        />
        <select
          aria-label={t("alertSettings.triggers.mode")}
          value={form.mode}
          onChange={(e) => setForm({ ...form, mode: e.target.value as PriceTriggerMode })}
          disabled={disabled}
        >
          <option value="once">{t("alertSettings.triggers.once")}</option>
          <option value="continuous">{t("alertSettings.triggers.continuous")}</option>
        </select>
        <input
          aria-label={t("alertSettings.triggers.note")}
          placeholder={t("alertSettings.triggers.note")}
          value={form.note}
          maxLength={200}
          onChange={(e) => setForm({ ...form, note: e.target.value })}
          disabled={disabled}
        />
        <button type="submit" disabled={disabled || busy || !formValid} title={disabledReason}>
          {editingId ? t("alertSettings.triggers.update") : t("alertSettings.triggers.add")}
        </button>
        {editingId && (
          <button type="button" onClick={cancelEdit}>
            {t("alertSettings.triggers.cancel")}
          </button>
        )}
      </form>
      {scoped && latestPrice != null && Number.isFinite(latestPrice) && (
        <p style={{ fontSize: "0.85em" }}>
          {t("alertSettings.triggers.latestPrice", { price: latestPrice.toFixed(2) })}
        </p>
      )}
      <p style={{ fontSize: "0.85em" }}>{t("alertSettings.triggers.modeHelp")}</p>

      {error && <p role="alert">{error}</p>}

      {visible.length === 0 ? (
        <p>
          {scoped
            ? t("alertSettings.triggers.instrumentEmpty", { ticker })
            : t("alertSettings.triggers.empty")}
        </p>
      ) : (
        <table>
          <thead>
            <tr>
              {!scoped && <th>{t("alertSettings.triggers.ticker")}</th>}
              <th>{t("alertSettings.triggers.when")}</th>
              <th>{t("alertSettings.triggers.mode")}</th>
              <th>{t("alertSettings.triggers.enabled")}</th>
              <th>{t("alertSettings.triggers.lastFired")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {visible.map((tr) => (
              <tr key={tr.id}>
                {!scoped && (
                  <td>
                    {tr.ticker}
                    {tr.note ? <div style={{ fontSize: "0.85em" }}>{tr.note}</div> : null}
                  </td>
                )}
                <td>
                  {t(`alertSettings.triggers.${tr.condition}`)} £{tr.price.toFixed(2)}
                  {scoped && tr.note ? (
                    <div style={{ fontSize: "0.85em" }}>{tr.note}</div>
                  ) : null}
                </td>
                <td>{t(`alertSettings.triggers.${tr.mode}`)}</td>
                <td>
                  <input
                    type="checkbox"
                    aria-label={`${t("alertSettings.triggers.enabled")} ${tr.ticker}`}
                    checked={tr.enabled}
                    disabled={disabled || busy}
                    onChange={(e) =>
                      void run(
                        () => updatePriceTrigger(identity, tr.id, { enabled: e.target.checked }),
                        t("alertSettings.triggers.saveError"),
                      )
                    }
                  />
                </td>
                <td>
                  {tr.last_triggered_at
                    ? `${new Date(tr.last_triggered_at).toLocaleString()} (£${(
                        tr.last_triggered_price ?? 0
                      ).toFixed(2)}, ×${tr.trigger_count})`
                    : "—"}
                </td>
                <td>
                  <button onClick={() => edit(tr)} disabled={disabled || busy}>
                    {t("alertSettings.triggers.edit")}
                  </button>{" "}
                  <button
                    onClick={() =>
                      void run(
                        () => deletePriceTrigger(identity, tr.id),
                        t("alertSettings.triggers.deleteError"),
                      )
                    }
                    disabled={disabled || busy}
                  >
                    {t("alertSettings.triggers.delete")}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
