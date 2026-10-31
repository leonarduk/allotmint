import { useState, type MouseEvent } from "react";
import { useTranslation } from "react-i18next";
import type { Sleeve } from "../types";
import { useDemoReadOnly } from "../hooks/useDemoReadOnly";
import tableStyles from "../styles/table.module.css";

const CORE_ID = "core";

/** One owner's sleeves and ticker tags, for tagging holdings in place (#9839). */
export type SleeveControl = {
  /** Every sleeve, core included. */
  sleeves: Sleeve[];
  /** Upper-cased ticker -> sleeve id; untagged tickers are in the core. */
  assignments: Record<string, string>;
  onAssign: (ticker: string, sleeveId: string) => Promise<void>;
  /** Upper-cased tickers the owner holds, when known; the instrument page offers the picker only for these. */
  heldTickers?: ReadonlySet<string>;
};

/** The sleeve a ticker is in; untagged or dangling tags fall back to the core, as on the backend. */
const sleeveOf = (control: SleeveControl, ticker: string): string => {
  const id = control.assignments[ticker.trim().toUpperCase()];
  return id && control.sleeves.some((s) => s.id === id) ? id : CORE_ID;
};

// The row itself selects the instrument; changing the sleeve must not.
const stop = (event: MouseEvent) => event.stopPropagation();

/** Sleeve picker for one holding plus its error; reuses the Sleeves panel's option labels. */
export function SleeveSelect({
  control,
  ticker,
  label,
}: {
  control: SleeveControl;
  ticker: string;
  /** Accessible name; defaults to "Sleeve for <ticker>". */
  label?: string;
}) {
  const { t } = useTranslation();
  const { demoReadOnly, reason } = useDemoReadOnly();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const change = async (sleeveId: string) => {
    setBusy(true);
    setError(null);
    try {
      await control.onAssign(ticker, sleeveId);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <select
        className="rounded border p-1"
        aria-label={label ?? t("sleeves.assign.sleeveFor", { ticker })}
        value={sleeveOf(control, ticker)}
        disabled={busy || demoReadOnly}
        title={reason()}
        onChange={(e) => void change(e.target.value)}
      >
        {control.sleeves.map((s) => (
          <option key={s.id} value={s.id}>
            {s.id === CORE_ID ? t("sleeves.core") : s.name}
          </option>
        ))}
      </select>
      {error && (
        <span role="alert" className="block text-xs text-red-600">
          {error}
        </span>
      )}
    </>
  );
}

/** Table cell with a sleeve picker for one holding. */
export function HoldingSleeveCell({ control, ticker }: { control: SleeveControl; ticker: string }) {
  return (
    <td className={tableStyles.cell} onClick={stop}>
      <SleeveSelect control={control} ticker={ticker} />
    </td>
  );
}
