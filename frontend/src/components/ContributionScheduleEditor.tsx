import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import {
  getContributionSchedule,
  getOwners,
  putContributionSchedule,
  type ContributionFrequency,
  type ContributionSource,
  type ScheduledContribution,
} from "../api";
import { useDemoReadOnly } from "../hooks/useDemoReadOnly";
import { minorToPounds, poundsToMinor } from "../lib/minorUnits";

const FREQUENCIES: ContributionFrequency[] = ["monthly", "quarterly", "annual"];
const SOURCES: ContributionSource[] = ["personal_relief_at_source", "personal_gross", "employer", "isa_subscription"];

// Same rule as backend is_isa_account(): ISA accounts take only isa_subscription.
const isIsaAccount = (account: string) => account.toLowerCase().includes("isa");

/** Keep the source consistent with the account kind when the account changes. */
function sourceForAccount(account: string, current: ContributionSource): ContributionSource {
  if (isIsaAccount(account)) return "isa_subscription";
  return current === "isa_subscription" ? "personal_relief_at_source" : current;
}

interface DraftRow {
  key: number;
  account: string;
  amount: string;
  frequency: ContributionFrequency;
  source: ContributionSource;
  expectedDay: string;
  startDate: string;
  endDate: string;
  label: string;
}

const toDraft = (item: ScheduledContribution, key: number): DraftRow => ({
  key,
  account: item.account,
  amount: minorToPounds(item.amount_minor),
  frequency: item.frequency,
  source: item.source,
  expectedDay: String(item.expected_day),
  startDate: item.start_date,
  endDate: item.end_date ?? "",
  label: item.label ?? "",
});

const blankDraft = (account: string, key: number): DraftRow => ({
  key,
  account,
  amount: "",
  frequency: "monthly",
  source: sourceForAccount(account, "personal_relief_at_source"),
  expectedDay: "1",
  startDate: new Date().toISOString().slice(0, 10),
  endDate: "",
  label: "",
});

/** Draft rows to the PUT payload, or the index of the first row whose £ amount is invalid. */
function toPayload(rows: DraftRow[]): ScheduledContribution[] | { badAmount: number } {
  const out: ScheduledContribution[] = [];
  for (const [index, row] of rows.entries()) {
    const amountMinor = poundsToMinor(row.amount);
    if (amountMinor === null) return { badAmount: index };
    out.push({
      account: row.account.trim(),
      amount_minor: amountMinor,
      frequency: row.frequency,
      source: row.source,
      expected_day: Number(row.expectedDay),
      start_date: row.startDate,
      end_date: row.endDate || null,
      label: row.label.trim() || null,
    });
  }
  return out;
}

const inputClass = "w-full rounded border border-[var(--surface-card-border)] bg-transparent p-1";
const buttonClass = "rounded border border-[var(--surface-muted-border)] px-3 py-1 text-sm disabled:opacity-50";

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label>
      {label}
      {children}
    </label>
  );
}

interface RowProps {
  row: DraftRow;
  index: number;
  accounts: string[];
  disabled: boolean;
  amountInvalid: boolean;
  onChange: (patch: Partial<DraftRow>) => void;
  onRemove: () => void;
}

function AccountInput({ row, accounts, onChange }: Pick<RowProps, "row" | "accounts" | "onChange">) {
  const { t } = useTranslation();
  const change = (account: string) => onChange({ account, source: sourceForAccount(account, row.source) });
  if (!accounts.length) {
    return <input className={inputClass} value={row.account} required maxLength={64} onChange={(e) => change(e.target.value)} />;
  }
  const options = !row.account || accounts.includes(row.account) ? accounts : [row.account, ...accounts];
  return (
    <select className={inputClass} value={row.account} required onChange={(e) => change(e.target.value)}>
      {!row.account && <option value="">{t("contributionSchedule.chooseAccount")}</option>}
      {options.map((account) => (
        <option key={account} value={account}>
          {account}
        </option>
      ))}
    </select>
  );
}

function AmountInput({ row, amountInvalid, onChange }: Pick<RowProps, "row" | "amountInvalid" | "onChange">) {
  const { t } = useTranslation();
  const errorId = `contribution-${row.key}-amount-error`;
  return (
    <>
      <input
        className={inputClass}
        inputMode="decimal"
        value={row.amount}
        required
        aria-invalid={amountInvalid}
        aria-describedby={amountInvalid ? errorId : undefined}
        onChange={(e) => onChange({ amount: e.target.value })}
      />
      {amountInvalid && (
        <span id={errorId} className="text-red-500">
          {t("contributionSchedule.amountInvalid")}
        </span>
      )}
    </>
  );
}

function OptionSelect<T extends string>(props: {
  value: T;
  options: T[];
  labelPrefix: string;
  describedBy?: string;
  onChange: (value: T) => void;
}) {
  const { t } = useTranslation();
  return (
    <select
      className={inputClass}
      value={props.value}
      aria-describedby={props.describedBy}
      onChange={(e) => props.onChange(e.target.value as T)}
    >
      {props.options.map((option) => (
        <option key={option} value={option}>
          {t(`${props.labelPrefix}.${option}`)}
        </option>
      ))}
    </select>
  );
}

function ScheduleRow({ row, index, accounts, disabled, amountInvalid, onChange, onRemove }: RowProps) {
  const { t } = useTranslation();
  const helpId = `contribution-${row.key}-source-help`;
  const text = (field: "startDate" | "endDate" | "label") => (e: { target: { value: string } }) =>
    onChange({ [field]: e.target.value });
  return (
    <fieldset className="mb-3 rounded border border-[var(--surface-card-border)] p-3" disabled={disabled}>
      <legend className="px-1 text-sm font-semibold">{t("contributionSchedule.rowLegend", { number: index + 1 })}</legend>
      <div className="grid gap-2 text-sm sm:grid-cols-2 lg:grid-cols-4">
        <Field label={t("contributionSchedule.account")}>
          <AccountInput row={row} accounts={accounts} onChange={onChange} />
        </Field>
        <Field label={t("contributionSchedule.amount")}>
          <AmountInput row={row} amountInvalid={amountInvalid} onChange={onChange} />
        </Field>
        <Field label={t("contributionSchedule.frequency")}>
          <OptionSelect value={row.frequency} options={FREQUENCIES} labelPrefix="contributionSchedule.frequencies" onChange={(frequency) => onChange({ frequency })} />
        </Field>
        <Field label={t("contributionSchedule.source")}>
          <OptionSelect value={row.source} options={SOURCES} labelPrefix="contributionSchedule.sources" describedBy={helpId} onChange={(source) => onChange({ source })} />
        </Field>
        <Field label={t("contributionSchedule.expectedDay")}>
          <input className={inputClass} type="number" min={1} max={31} required value={row.expectedDay} onChange={(e) => onChange({ expectedDay: e.target.value })} />
        </Field>
        <Field label={t("contributionSchedule.startDate")}>
          <input className={inputClass} type="date" required value={row.startDate} onChange={text("startDate")} />
        </Field>
        <Field label={t("contributionSchedule.endDate")}>
          <input className={inputClass} type="date" value={row.endDate} onChange={text("endDate")} />
        </Field>
        <Field label={t("contributionSchedule.label")}>
          <input className={inputClass} maxLength={120} value={row.label} onChange={text("label")} />
        </Field>
      </div>
      <p id={helpId} className="mt-2 text-xs opacity-75">
        {t(`contributionSchedule.sourceHelp.${row.source}`)}
      </p>
      <button type="button" className="mt-2 text-sm text-red-600 underline" onClick={onRemove}>
        {t("contributionSchedule.remove", { number: index + 1 })}
      </button>
    </fieldset>
  );
}

/** Load the schedule and the owner's account names; keep the draft rows. */
function useScheduleDraft(owner: string) {
  const [rows, setRows] = useState<DraftRow[] | null>(null);
  const [accounts, setAccounts] = useState<string[]>([]);
  const [loadError, setLoadError] = useState(false);
  const keyRef = useRef(0);
  const nextKey = () => keyRef.current++;

  useEffect(() => {
    let active = true;
    setRows(null);
    setLoadError(false);
    getContributionSchedule(owner)
      .then((schedule) => {
        if (active) setRows(schedule.contributions.map((item) => toDraft(item, keyRef.current++)));
      })
      .catch(() => {
        if (active) setLoadError(true);
      });
    // Account names only seed the account picker; without them the field is free text.
    getOwners()
      .then((owners) => {
        if (active) setAccounts(owners.find((o) => o.owner === owner)?.accounts ?? []);
      })
      .catch(() => {
        if (active) setAccounts([]);
      });
    return () => {
      active = false;
    };
  }, [owner]);

  return { rows, setRows, accounts, loadError, nextKey };
}

/**
 * Edit the owner's expected contributions (#10496), saved as integer pence through
 * PUT /allowance-guardian/{owner}/schedule. The backend's 400 validation detail is
 * shown verbatim beside the form; `onSaved` lets the page refresh the guardian report.
 */
export default function ContributionScheduleEditor({ owner, onSaved }: { owner: string; onSaved?: () => void }) {
  const { t } = useTranslation();
  const { demoReadOnly, reason } = useDemoReadOnly();
  const { rows, setRows, accounts, loadError, nextKey } = useScheduleDraft(owner);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [badAmount, setBadAmount] = useState<number | null>(null);
  const [saved, setSaved] = useState(false);
  const locked = demoReadOnly || saving;

  const edit = (next: (prev: DraftRow[]) => DraftRow[]) => {
    setSaved(false);
    setBadAmount(null);
    setRows((prev) => (prev ? next(prev) : prev));
  };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    const payload = toPayload(rows ?? []);
    if (!Array.isArray(payload)) {
      setSaveError(null);
      setBadAmount(payload.badAmount);
      return;
    }
    setSaveError(null);
    setSaving(true);
    try {
      const result = await putContributionSchedule(owner, { owner, contributions: payload });
      setRows(result.contributions.map((item) => toDraft(item, nextKey())));
      setSaved(true);
      onSaved?.();
    } catch (err) {
      setSaveError(err instanceof Error && err.message ? err.message : t("contributionSchedule.saveFailed"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="mt-6 rounded border border-[var(--surface-card-border)] p-4" aria-labelledby="contribution-schedule-title">
      <h2 id="contribution-schedule-title" className="mb-1 text-xl">
        {t("contributionSchedule.title")}
      </h2>
      <p className="mb-3 text-sm opacity-75">{t("contributionSchedule.intro")}</p>
      {loadError && <p className="text-red-500">{t("contributionSchedule.loadFailed")}</p>}
      {!rows && !loadError && <p role="status">{t("app.loading")}</p>}
      {rows && (
        <form onSubmit={handleSubmit} aria-label={t("contributionSchedule.title")}>
          {rows.length === 0 && <p className="mb-3 text-sm">{t("contributionSchedule.empty")}</p>}
          {rows.map((row, index) => (
            <ScheduleRow
              key={row.key}
              row={row}
              index={index}
              accounts={accounts}
              disabled={locked}
              amountInvalid={badAmount === index}
              onChange={(patch) => edit((prev) => prev.map((r) => (r.key === row.key ? { ...r, ...patch } : r)))}
              onRemove={() => edit((prev) => prev.filter((r) => r.key !== row.key))}
            />
          ))}
          {saveError && (
            <p role="alert" className="mb-2 text-sm text-red-500">
              {t("contributionSchedule.rejected", { detail: saveError })}
            </p>
          )}
          {saved && (
            <p role="status" className="mb-2 text-sm text-green-600">
              {t("contributionSchedule.saved")}
            </p>
          )}
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              className={buttonClass}
              disabled={locked}
              title={reason()}
              onClick={() => edit((prev) => [...prev, blankDraft(accounts[0] ?? "", nextKey())])}
            >
              {t("contributionSchedule.add")}
            </button>
            <button type="submit" className={buttonClass} disabled={locked} title={reason()}>
              {saving ? t("contributionSchedule.saving") : t("contributionSchedule.save")}
            </button>
          </div>
        </form>
      )}
    </section>
  );
}
