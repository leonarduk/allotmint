import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import {
  getBot,
  getBotRun,
  getBotRuns,
  getBots,
  runBotNow,
  updateBotSettings,
  type BotDetail,
  type BotRun,
  type BotRunStatus,
  type BotSettingsSchemaProperty,
  type BotSummary,
} from '../api';
import tableStyles from '../styles/table.module.css';

const POLL_INTERVAL_MS = 2000;
// Stop polling after this long; the longest bot timeout is 15 minutes, so a
// run still "running" by then crashed without updating its record.
const POLL_MAX_MS = 20 * 60 * 1000;

const STATUS_CLASSES: Record<BotRunStatus | 'never', string> = {
  ok: 'bg-green-100 text-green-800',
  partial: 'bg-amber-100 text-amber-800',
  failed: 'bg-red-100 text-red-800',
  skipped: 'bg-gray-100 text-gray-700',
  running: 'bg-blue-100 text-blue-800',
  never: 'bg-gray-100 text-gray-500',
};

function errorMessage(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

function formatTime(value?: string | null): string {
  return value ? new Date(value).toLocaleString() : '—';
}

export function StatusBadge({ status }: { status?: BotRunStatus | null }) {
  const { t } = useTranslation();
  const key = status ?? 'never';
  return (
    <span
      className={`rounded px-2 py-0.5 text-xs font-medium ${STATUS_CLASSES[key]}`}
      data-testid="bot-status"
    >
      {t(`bots.status.${key}`)}
    </span>
  );
}

function BotList({
  bots,
  selected,
  onSelect,
}: {
  bots: BotSummary[];
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="overflow-x-auto">
      <table className={`${tableStyles.table} w-full`}>
        <thead>
          <tr>
            <th className={tableStyles.cell}>{t('bots.columns.bot')}</th>
            <th className={tableStyles.cell}>{t('bots.columns.kind')}</th>
            <th className={tableStyles.cell}>{t('bots.columns.lastRun')}</th>
            <th className={tableStyles.cell}>{t('bots.columns.result')}</th>
            <th className={tableStyles.cell}>{t('bots.columns.nextRun')}</th>
          </tr>
        </thead>
        <tbody>
          {bots.map((bot) => (
            <tr
              key={bot.id}
              className={`cursor-pointer ${selected === bot.id ? 'font-semibold' : ''}`}
              onClick={() => onSelect(bot.id)}
            >
              <td className={tableStyles.cell}>
                <button
                  type="button"
                  className="text-left underline-offset-2 hover:underline"
                >
                  {bot.name}
                </button>
                {!bot.enabled && (
                  <span className="ml-2 text-xs opacity-70">
                    ({t('bots.disabled')})
                  </span>
                )}
              </td>
              <td className={tableStyles.cell}>{t(`bots.kind.${bot.kind}`)}</td>
              <td className={tableStyles.cell}>
                <StatusBadge
                  status={bot.running ? 'running' : bot.last_run?.status}
                />{' '}
                <span className="text-sm">
                  {formatTime(bot.last_run?.started_at)}
                </span>
              </td>
              <td className={tableStyles.cell}>
                {bot.last_run?.summary ?? '—'}
              </td>
              <td className={tableStyles.cell}>{formatTime(bot.next_run)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RunUsage({ run }: { run: BotRun }) {
  const { t } = useTranslation();
  if (!run.model && run.tokens_in == null && run.cost_usd == null) return null;
  return (
    <p className="text-xs opacity-80">
      {t('bots.usage', {
        model: run.model ?? '—',
        tokensIn: run.tokens_in ?? 0,
        tokensOut: run.tokens_out ?? 0,
        cost: (run.cost_usd ?? 0).toFixed(4),
      })}
    </p>
  );
}

function RunHistory({ runs }: { runs: BotRun[] }) {
  const { t } = useTranslation();
  if (runs.length === 0) return <p>{t('bots.noRuns')}</p>;
  return (
    <ul className="space-y-2">
      {runs.map((run) => (
        <li key={run.id} className="rounded border p-2" data-testid="bot-run">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <StatusBadge status={run.status} />
            <span>{formatTime(run.started_at)}</span>
            <span className="opacity-70">
              {t(`bots.trigger.${run.trigger}`)}
            </span>
            {run.duration_seconds != null && (
              <span className="opacity-70">
                {t('bots.duration', {
                  seconds: run.duration_seconds.toFixed(1),
                })}
              </span>
            )}
          </div>
          {run.summary && <p className="text-sm">{run.summary}</p>}
          <RunUsage run={run} />
          {run.report && (
            <details className="text-xs">
              <summary>{t('bots.report')}</summary>
              <pre className="overflow-x-auto whitespace-pre-wrap">
                {JSON.stringify(run.report, null, 2)}
              </pre>
            </details>
          )}
          {run.error && (
            <pre className="mt-1 overflow-x-auto whitespace-pre-wrap text-xs text-red-700">
              {run.error}
            </pre>
          )}
        </li>
      ))}
    </ul>
  );
}

function isNullable(prop: BotSettingsSchemaProperty): boolean {
  return Boolean(prop.anyOf?.some((option) => option.type === 'null'));
}

function fieldType(prop: BotSettingsSchemaProperty): string {
  if (prop.enum) return 'enum';
  return (
    prop.type ??
    prop.anyOf?.find((option) => option.type !== 'null')?.type ??
    'string'
  );
}

function SettingField({
  name,
  prop,
  value,
  disabled,
  onChange,
}: {
  name: string;
  prop: BotSettingsSchemaProperty;
  value: unknown;
  disabled: boolean;
  onChange: (value: unknown) => void;
}) {
  const label = prop.description ?? prop.title ?? name;
  const type = fieldType(prop);
  if (type === 'boolean') {
    return (
      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          name={name}
          checked={Boolean(value)}
          disabled={disabled}
          onChange={(e) => onChange(e.target.checked)}
        />
        {label}
      </label>
    );
  }
  if (type === 'enum') {
    return (
      <label className="flex flex-col text-sm">
        {label}
        <select
          name={name}
          value={String(value ?? '')}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
        >
          {prop.enum?.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      </label>
    );
  }
  const numeric = type === 'number' || type === 'integer';
  return (
    <label className="flex flex-col text-sm">
      {label}
      <input
        type={numeric ? 'number' : 'text'}
        name={name}
        step={type === 'integer' ? 1 : 'any'}
        min={prop.minimum ?? prop.exclusiveMinimum}
        max={prop.maximum ?? prop.exclusiveMaximum}
        value={value == null ? '' : String(value)}
        disabled={disabled}
        onChange={(e) => {
          const raw = e.target.value;
          if (raw === '') onChange(isNullable(prop) ? null : raw);
          else onChange(numeric ? Number(raw) : raw);
        }}
      />
    </label>
  );
}

function validationMessages(e: unknown): string[] {
  const detail = (e as { body?: { detail?: unknown } })?.body?.detail;
  if (Array.isArray(detail)) {
    return detail.map((item: { loc?: unknown[]; msg?: string }) =>
      [item.loc?.filter((part) => part !== 'body').join('.'), item.msg]
        .filter(Boolean)
        .join(': ')
    );
  }
  return [errorMessage(e)];
}

function SettingsForm({
  bot,
  onSaved,
}: {
  bot: BotDetail;
  onSaved: (bot: BotDetail) => void;
}) {
  const { t } = useTranslation();
  const [values, setValues] = useState<Record<string, unknown>>(bot.settings);
  const [errors, setErrors] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  // Unsaved edits survive the panel re-fetching (e.g. after a run finishes);
  // the form only follows the server's values while it has none.
  const [dirty, setDirty] = useState(false);
  useEffect(() => {
    if (!dirty) setValues(bot.settings);
  }, [bot.settings, dirty]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setErrors([]);
    setSaved(false);
    try {
      onSaved(await updateBotSettings(bot.id, values));
      setDirty(false);
      setSaved(true);
    } catch (err) {
      setErrors(validationMessages(err));
    } finally {
      setSaving(false);
    }
  };

  const properties = Object.entries(bot.settings_schema.properties ?? {});
  return (
    <form
      onSubmit={submit}
      className="space-y-2"
      aria-label={t('bots.settings')}
    >
      {properties.map(([name, prop]) => (
        <SettingField
          key={name}
          name={name}
          prop={prop}
          value={values[name]}
          disabled={!bot.can_manage || saving}
          onChange={(value) => {
            setDirty(true);
            setValues((prev) => ({ ...prev, [name]: value }));
          }}
        />
      ))}
      {errors.map((message) => (
        <p key={message} role="alert" className="text-sm text-red-600">
          {message}
        </p>
      ))}
      {saved && <p className="text-sm text-green-700">{t('bots.saved')}</p>}
      {bot.can_manage && (
        <button
          type="submit"
          className="rounded border px-3 py-1"
          disabled={saving}
        >
          {t('bots.saveSettings')}
        </button>
      )}
    </form>
  );
}

/** Polls a Run now run until it leaves "running", then calls onDone. */
function useRunPoller(onDone: () => void) {
  const { t } = useTranslation();
  const [active, setActive] = useState<{ botId: string; runId: string } | null>(
    null
  );
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!active) return undefined;
    let cancelled = false;
    const startedAt = Date.now();
    const timer = setInterval(async () => {
      if (Date.now() - startedAt > POLL_MAX_MS) {
        setError(t('bots.pollTimeout'));
        setActive(null);
        return;
      }
      try {
        const run = await getBotRun(active.botId, active.runId);
        if (cancelled || run.status === 'running') return;
        setActive(null);
        onDone();
      } catch (e) {
        if (cancelled) return;
        setError(errorMessage(e));
        setActive(null);
      }
    }, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [active, onDone, t]);

  return { polling: active !== null, start: setActive, error };
}

function BotDetailPanel({
  botId,
  onChanged,
}: {
  botId: string;
  onChanged: () => void;
}) {
  const { t } = useTranslation();
  const [bot, setBot] = useState<BotDetail | null>(null);
  const [runs, setRuns] = useState<BotRun[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [detail, history] = await Promise.all([
        getBot(botId),
        getBotRuns(botId),
      ]);
      setBot(detail);
      setRuns(history);
      setError(null);
    } catch (e) {
      setError(errorMessage(e));
    }
  }, [botId]);

  const refreshAll = useCallback(() => {
    void load(); // load() reports its own errors via setError
    onChanged();
  }, [load, onChanged]);
  const poller = useRunPoller(refreshAll);

  useEffect(() => {
    void load(); // load() reports its own errors via setError
  }, [load]);

  const runNow = async () => {
    setError(null);
    try {
      const run = await runBotNow(botId);
      poller.start({ botId, runId: run.id });
      refreshAll();
    } catch (e) {
      setError(errorMessage(e));
    }
  };

  if (!bot)
    return error ? <p role="alert">{error}</p> : <p>{t('common.loading')}</p>;
  return (
    <section className="mt-6 rounded border p-4" aria-label={bot.name}>
      <h3 className="text-lg font-semibold">{bot.name}</h3>
      <p className="mb-2 text-sm">{bot.description}</p>
      <p className="text-sm opacity-80">
        {t('bots.scheduleLine', {
          schedule: bot.schedule ?? t('bots.onEvent'),
          scope: t(`bots.scope.${bot.scope}`),
        })}
      </p>
      {bot.can_manage && (
        <button
          type="button"
          className="my-3 rounded border px-3 py-1"
          onClick={() => void runNow()}
          disabled={bot.running || poller.polling}
        >
          {bot.running || poller.polling ? t('bots.running') : t('bots.runNow')}
        </button>
      )}
      {(error || poller.error) && (
        <p role="alert" className="text-sm text-red-600">
          {error ?? poller.error}
        </p>
      )}
      <h4 className="mt-4 font-semibold">{t('bots.settings')}</h4>
      {!bot.can_manage && (
        <p className="text-xs opacity-70">{t('bots.adminOnly')}</p>
      )}
      <SettingsForm
        bot={bot}
        onSaved={(updated) => {
          setBot(updated);
          onChanged();
        }}
      />
      <h4 className="mt-4 font-semibold">{t('bots.history')}</h4>
      <RunHistory runs={runs} />
    </section>
  );
}

export default function Bots() {
  const { t } = useTranslation();
  const [bots, setBots] = useState<BotSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  const loadBots = useCallback(async () => {
    try {
      setBots(await getBots());
      setError(null);
    } catch (e) {
      setError(errorMessage(e));
    }
  }, []);
  const reload = useCallback(() => {
    void loadBots(); // loadBots() reports its own errors via setError
  }, [loadBots]);

  useEffect(reload, [reload]);

  return (
    <div className="container mx-auto max-w-5xl p-4">
      <h2 className="mb-2 text-xl md:text-2xl">{t('bots.title')}</h2>
      <p className="mb-4 text-sm opacity-80">{t('bots.intro')}</p>
      {error && (
        <p role="alert" className="text-red-600">
          {t('bots.loadError')} {error}
        </p>
      )}
      {!bots && !error && <p>{t('common.loading')}</p>}
      {bots && (
        <BotList bots={bots} selected={selected} onSelect={setSelected} />
      )}
      {selected && (
        <BotDetailPanel key={selected} botId={selected} onChanged={reload} />
      )}
    </div>
  );
}
