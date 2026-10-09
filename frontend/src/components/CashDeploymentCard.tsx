import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  createCashDeploymentSchedule,
  deleteCashDeploymentSchedule,
  getCashDeployment,
  updateCashDeploymentSchedule,
} from '../api';
import { allocationKeyLabel } from '../lib/assetClass';
import { gbp, orderListText, pounds, units } from '../lib/cashDeployment';
import { localDateISO } from '../lib/date';
import type {
  CashDeploymentEntry,
  CashDeploymentRun,
  CashDeploymentSchedule,
  CashDeploymentScheduleInput,
  CashDeploymentTranche,
  RebalanceAccount,
} from '../types';

const errorText = (error: unknown) =>
  error instanceof Error ? error.message : String(error);

const INPUT = 'rounded border p-1';
const SMALL_BUTTON = 'rounded bg-gray-200 px-2 py-1 text-sm text-slate-900';

function OrderTable({ tranche }: { tranche: CashDeploymentTranche }) {
  const { t } = useTranslation();
  return (
    <table className="mb-1 w-full text-left text-sm">
      <thead>
        <tr>
          <th>{t('cashDeployment.assetClass')}</th>
          <th>{t('cashDeployment.vehicle')}</th>
          <th>{t('cashDeployment.amount')}</th>
          <th>{t('cashDeployment.price')}</th>
          <th>{t('cashDeployment.units')}</th>
        </tr>
      </thead>
      <tbody>
        {tranche.orders.map((o) => (
          <tr key={o.asset_class}>
            <td>{allocationKeyLabel(o.asset_class)}</td>
            <td>
              {o.ticker ?? o.vehicle_note ?? t('cashDeployment.noVehicle')}
            </td>
            <td>{pounds(o.amount_minor)}</td>
            <td>{o.price_gbp != null ? gbp.format(o.price_gbp) : '-'}</td>
            <td>
              {o.indicative_units != null
                ? units.format(o.indicative_units)
                : '-'}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function OrderList({ tranche }: { tranche: CashDeploymentTranche }) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(orderListText(tranche));
      setCopied(true);
    } catch (err) {
      console.error('Could not copy the order list', err);
    }
  };
  return (
    <div className="mt-2">
      <p className="text-sm font-medium">
        {t('cashDeployment.currentTranche', {
          number: tranche.index + 1,
          date: tranche.due_date,
        })}
      </p>
      <p className="mb-1 text-xs text-slate-500 dark:text-slate-400">
        {t('cashDeployment.orderLabel')}
      </p>
      <OrderTable tranche={tranche} />
      {tranche.keep_as_cash_minor > 0 && (
        <p className="text-xs">
          {t('cashDeployment.keepAsCash', {
            amount: pounds(tranche.keep_as_cash_minor),
          })}
        </p>
      )}
      <button type="button" className={SMALL_BUTTON} onClick={copy}>
        {copied ? t('cashDeployment.copied') : t('cashDeployment.copy')}
      </button>
    </div>
  );
}

function TrancheTable({ entry }: { entry: CashDeploymentEntry }) {
  const { t } = useTranslation();
  if (!entry.progress) return null;
  return (
    <table className="w-full text-left text-sm">
      <thead>
        <tr>
          <th>{t('cashDeployment.dueDate')}</th>
          <th>{t('cashDeployment.amount')}</th>
          <th>{t('cashDeployment.invested')}</th>
          <th>{t('cashDeployment.status')}</th>
        </tr>
      </thead>
      <tbody>
        {entry.progress.tranches.map((row) => (
          <tr key={row.index} className={row.overdue ? 'text-amber-700' : ''}>
            <td>{row.due_date}</td>
            <td>{pounds(row.amount_minor)}</td>
            <td>{pounds(row.invested_minor)}</td>
            <td>{t(`cashDeployment.${row.status}`)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function toInput(
  schedule: CashDeploymentSchedule
): CashDeploymentScheduleInput {
  const { account, total_amount_minor, tranches, cadence, start_date } =
    schedule;
  const { target_source, status } = schedule;
  return {
    account,
    total_amount_minor,
    tranches,
    cadence,
    start_date,
    target_source,
    status,
  };
}

function ScheduleHeader({
  schedule,
  onChange,
  onDelete,
}: {
  schedule: CashDeploymentSchedule;
  onChange: (body: CashDeploymentScheduleInput) => void;
  onDelete: () => void;
}) {
  const { t } = useTranslation();
  const paused = schedule.status === 'paused';
  const toggle = () =>
    onChange({ ...toInput(schedule), status: paused ? 'active' : 'paused' });
  return (
    <div className="flex flex-wrap items-center justify-between gap-2">
      <h3 className="font-medium">
        {t('cashDeployment.heading', {
          account: schedule.account,
          total: pounds(schedule.total_amount_minor),
          tranches: schedule.tranches,
          cadence: t(`cashDeployment.${schedule.cadence}`),
          start: schedule.start_date,
        })}{' '}
        · {t(`cashDeployment.${schedule.status}`)}
      </h3>
      <div className="flex gap-2">
        <button type="button" className={SMALL_BUTTON} onClick={toggle}>
          {paused ? t('cashDeployment.resume') : t('cashDeployment.pause')}
        </button>
        <button type="button" className={SMALL_BUTTON} onClick={onDelete}>
          {t('cashDeployment.delete')}
        </button>
      </div>
    </div>
  );
}

function ScheduleView({
  entry,
  onChange,
  onDelete,
}: {
  entry: CashDeploymentEntry;
  onChange: (body: CashDeploymentScheduleInput) => void;
  onDelete: () => void;
}) {
  const { t } = useTranslation();
  const { schedule, progress } = entry;
  return (
    <article className="mb-4 rounded border p-3" aria-label={schedule.id}>
      <ScheduleHeader
        schedule={schedule}
        onChange={onChange}
        onDelete={onDelete}
      />
      {entry.error && <p className="text-sm text-red-600">{entry.error}</p>}
      {progress && (
        <>
          <p className="text-sm">{progress.summary}</p>
          <p className="mb-2 text-xs text-slate-500 dark:text-slate-400">
            {t('cashDeployment.progress', {
              deployed: pounds(progress.deployed_minor),
              total: pounds(progress.total_amount_minor),
              remaining: pounds(progress.remaining_minor),
              interest: pounds(progress.interest_minor),
            })}
          </p>
        </>
      )}
      {entry.tranche && <OrderList tranche={entry.tranche} />}
      <details className="mt-2">
        <summary className="cursor-pointer text-sm">
          {t('cashDeployment.tranches')}
        </summary>
        <TrancheTable entry={entry} />
      </details>
    </article>
  );
}

function emptyInput(accountId: string): CashDeploymentScheduleInput {
  return {
    account: accountId,
    total_amount_minor: 0,
    tranches: 12,
    cadence: 'monthly',
    start_date: localDateISO(),
    target_source: 'plan',
    status: 'active',
  };
}

function Field({
  id,
  label,
  children,
}: {
  id: string;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="flex flex-col text-sm" htmlFor={id}>
      {label}
      {children}
    </label>
  );
}

function Choice<T extends string>({
  id,
  label,
  value,
  options,
  onChange,
}: {
  id: string;
  label: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
}) {
  return (
    <Field id={id} label={label}>
      <select
        id={id}
        className={INPUT}
        value={value}
        onChange={(e) => onChange(e.target.value as T)}
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </Field>
  );
}

type Patch = (patch: Partial<CashDeploymentScheduleInput>) => void;

function TimingFields({
  form,
  set,
}: {
  form: CashDeploymentScheduleInput;
  set: Patch;
}) {
  const { t } = useTranslation();
  const cadences = (['weekly', 'monthly', 'quarterly'] as const).map((c) => ({
    value: c,
    label: t(`cashDeployment.${c}`),
  }));
  const sources = [
    { value: 'plan' as const, label: t('cashDeployment.targetPlan') },
    { value: 'policy' as const, label: t('cashDeployment.targetPolicy') },
  ];
  return (
    <>
      <Field id="cd-tranches" label={t('cashDeployment.tranches')}>
        <input
          id="cd-tranches"
          type="number"
          min="1"
          max="120"
          className={`${INPUT} w-20`}
          value={form.tranches}
          onChange={(e) => set({ tranches: parseInt(e.target.value, 10) || 0 })}
        />
      </Field>
      <Choice
        id="cd-cadence"
        label={t('cashDeployment.cadence')}
        value={form.cadence}
        options={cadences}
        onChange={(cadence) => set({ cadence })}
      />
      <Field id="cd-start" label={t('cashDeployment.startDate')}>
        <input
          id="cd-start"
          type="date"
          className={INPUT}
          value={form.start_date}
          onChange={(e) => set({ start_date: e.target.value })}
        />
      </Field>
      <Choice
        id="cd-target"
        label={t('cashDeployment.targetSource')}
        value={form.target_source}
        options={sources}
        onChange={(target_source) => set({ target_source })}
      />
    </>
  );
}

/** The owner enters their own schedule; the defaults are only neutral starting values to edit. */
function ScheduleForm({
  accounts,
  onSubmit,
}: {
  accounts: RebalanceAccount[];
  onSubmit: (body: CashDeploymentScheduleInput) => Promise<boolean>;
}) {
  const { t } = useTranslation();
  const [form, setForm] = useState(() => emptyInput(accounts[0]?.id ?? ''));
  const [total, setTotal] = useState('');
  const set: Patch = (patch) => setForm((prev) => ({ ...prev, ...patch }));
  const pence = Math.round(parseFloat(total) * 100);
  const valid = pence > 0 && form.tranches >= 1 && Boolean(form.account);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (await onSubmit({ ...form, total_amount_minor: pence })) setTotal('');
  };
  return (
    <form
      onSubmit={submit}
      className="flex flex-wrap items-end gap-3"
      aria-label={t('cashDeployment.create')}
    >
      <Choice
        id="cd-account"
        label={t('cashDeployment.account')}
        value={form.account}
        options={accounts.map((a) => ({ value: a.id, label: a.label }))}
        onChange={(account) => set({ account })}
      />
      <Field id="cd-total" label={t('cashDeployment.total')}>
        <input
          id="cd-total"
          type="number"
          min="0"
          step="any"
          className={`${INPUT} w-32`}
          value={total}
          onChange={(e) => setTotal(e.target.value)}
        />
      </Field>
      <TimingFields form={form} set={set} />
      <button
        type="submit"
        disabled={!valid}
        className="rounded bg-blue-500 px-4 py-2 text-white disabled:opacity-50"
      >
        {t('cashDeployment.save')}
      </button>
    </form>
  );
}

function useCashDeployment(owner: string) {
  const [run, setRun] = useState<CashDeploymentRun | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    try {
      setRun(await getCashDeployment(owner));
      setError(null);
    } catch (err) {
      setError(errorText(err));
    }
  }, [owner]);
  useEffect(() => {
    setRun(null);
    void load();
  }, [load]);
  return { run, error, load };
}

function Messages({
  run,
  error,
  actionError,
}: {
  run: CashDeploymentRun | null;
  error: string | null;
  actionError: string | null;
}) {
  const { t } = useTranslation();
  return (
    <>
      {error && (
        <p className="text-sm text-red-600">
          {t('cashDeployment.loadError', { message: error })}
        </p>
      )}
      {actionError && (
        <p className="text-sm text-red-600">
          {t('cashDeployment.actionError', { message: actionError })}
        </p>
      )}
      {!run && !error && (
        <p className="text-sm text-slate-500">{t('cashDeployment.loading')}</p>
      )}
      {run?.warnings.map((w) => (
        <p key={w} className="text-sm text-amber-700">
          {w}
        </p>
      ))}
      {run && run.schedules.length === 0 && (
        <p className="text-sm">{t('cashDeployment.none')}</p>
      )}
    </>
  );
}

/**
 * The owner's cash deployment schedules (#10480): progress against the
 * schedule they chose, and the current tranche's draft order list per their
 * plan. Nothing here places a trade.
 */
export default function CashDeploymentCard({
  owner,
  accounts,
}: {
  owner: string;
  accounts: RebalanceAccount[];
}) {
  const { t } = useTranslation();
  const { run, error, load } = useCashDeployment(owner);
  const [actionError, setActionError] = useState<string | null>(null);
  // Resolves true once the change is saved, so the form knows to clear itself.
  const act = async (action: () => Promise<unknown>): Promise<boolean> => {
    try {
      await action();
    } catch (err) {
      setActionError(errorText(err));
      return false;
    }
    setActionError(null);
    await load();
    return true;
  };
  return (
    <section
      className="mb-6 rounded border p-4"
      aria-label={t('cashDeployment.title')}
    >
      <h2 className="text-xl">{t('cashDeployment.title')}</h2>
      <p className="mb-2 text-xs text-slate-500 dark:text-slate-400">
        {t('cashDeployment.help')}
      </p>
      <Messages run={run} error={error} actionError={actionError} />
      {run?.schedules.map((entry) => (
        <ScheduleView
          key={entry.schedule.id}
          entry={entry}
          onChange={(body) =>
            act(() =>
              updateCashDeploymentSchedule(owner, entry.schedule.id, body)
            )
          }
          onDelete={() =>
            act(() => deleteCashDeploymentSchedule(owner, entry.schedule.id))
          }
        />
      ))}
      <h3 className="mb-1 mt-2 font-medium">{t('cashDeployment.create')}</h3>
      <ScheduleForm
        accounts={accounts}
        onSubmit={(body) =>
          act(() => createCashDeploymentSchedule(owner, body))
        }
      />
    </section>
  );
}
