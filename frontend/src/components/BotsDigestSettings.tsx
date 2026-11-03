import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import {
  getBots,
  getBotsDigestSettings,
  updateBotsDigestSettings,
  type BotSummary,
  type BotsDigestSettings as Settings,
  type BotsDigestSeverity,
} from '../api';

const SEVERITIES: BotsDigestSeverity[] = ['high', 'medium', 'low', 'info'];
const TOGGLES = [
  'email_enabled',
  'telegram_enabled',
  'include_balances',
  'send_when_empty',
] as const;

type Load =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'error' }
  | { kind: 'ready'; settings: Settings; bots: BotSummary[] };

/** 422 details from the settings API as "field: message" lines. */
function errorLines(e: unknown): string[] {
  const detail = (e as { body?: { detail?: unknown } })?.body?.detail;
  if (Array.isArray(detail)) {
    return detail.map((item: { loc?: unknown[]; msg?: string }) =>
      [item.loc?.join('.'), item.msg].filter(Boolean).join(': ')
    );
  }
  return [e instanceof Error ? e.message : String(e)];
}

/** ``severities`` with ``severity`` added or removed, in a stable order. */
function toggled(
  severities: BotsDigestSeverity[],
  severity: BotsDigestSeverity,
  on: boolean
): BotsDigestSeverity[] {
  const next = new Set(severities);
  if (on) next.add(severity);
  else next.delete(severity);
  return SEVERITIES.filter((s) => next.has(s));
}

/** Without any severity a bot is left out, so it stays digest-only. */
function withAlerts(
  alerts: Settings['alert_immediately_for'],
  botId: string,
  severities: BotsDigestSeverity[]
): Settings['alert_immediately_for'] {
  const next = { ...alerts };
  if (severities.length) next[botId] = severities;
  else delete next[botId];
  return next;
}

function AlertTable({
  bots,
  alerts,
  onChange,
}: {
  bots: BotSummary[];
  alerts: Settings['alert_immediately_for'];
  onChange: (alerts: Settings['alert_immediately_for']) => void;
}) {
  const { t } = useTranslation();
  return (
    <fieldset>
      <legend>{t('botsDigest.settings.alertImmediately')}</legend>
      <p className="muted">{t('botsDigest.settings.alertImmediatelyHelp')}</p>
      <table>
        <thead>
          <tr>
            <th scope="col">{t('botsDigest.settings.bot')}</th>
            {SEVERITIES.map((s) => (
              <th key={s} scope="col">
                {t(`botsDigest.severity.${s}`)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {bots.map((bot) => {
            const current = alerts[bot.id] ?? [];
            return (
              <tr key={bot.id}>
                <th scope="row">{bot.name}</th>
                {SEVERITIES.map((s) => (
                  <td key={s}>
                    <input
                      type="checkbox"
                      aria-label={`${bot.name}: ${t(`botsDigest.severity.${s}`)}`}
                      checked={current.includes(s)}
                      onChange={(e) =>
                        onChange(
                          withAlerts(
                            alerts,
                            bot.id,
                            toggled(current, s, e.target.checked)
                          )
                        )
                      }
                    />
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </fieldset>
  );
}

function SettingsForm({
  owner,
  initial,
  bots,
}: {
  owner: string;
  initial: Settings;
  bots: BotSummary[];
}) {
  const { t } = useTranslation();
  const [values, setValues] = useState<Settings>(initial);
  const [errors, setErrors] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const set = (patch: Partial<Settings>) => {
    setSaved(false);
    setValues((prev) => ({ ...prev, ...patch }));
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setErrors([]);
    try {
      setValues(await updateBotsDigestSettings(owner, values));
      setSaved(true);
    } catch (err) {
      setErrors(errorLines(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={submit} aria-label={t('botsDigest.settings.title')}>
      <label>
        {t('botsDigest.settings.period')}{' '}
        <select
          value={values.period}
          onChange={(e) =>
            set({ period: e.target.value as Settings['period'] })
          }
        >
          <option value="weekly">{t('botsDigest.settings.weekly')}</option>
          <option value="monthly">{t('botsDigest.settings.monthly')}</option>
        </select>
      </label>
      {TOGGLES.map((name) => (
        <label key={name} style={{ display: 'block' }}>
          <input
            type="checkbox"
            checked={values[name]}
            onChange={(e) => set({ [name]: e.target.checked })}
          />{' '}
          {t(`botsDigest.settings.${name}`)}
        </label>
      ))}
      <label style={{ display: 'block' }}>
        {t('botsDigest.settings.per_bot_cap')}{' '}
        <input
          type="number"
          min={1}
          max={50}
          step={1}
          value={values.per_bot_cap}
          onChange={(e) => set({ per_bot_cap: Number(e.target.value) })}
        />
      </label>
      <AlertTable
        bots={bots}
        alerts={values.alert_immediately_for}
        onChange={(alerts) => set({ alert_immediately_for: alerts })}
      />
      {errors.map((message) => (
        <p key={message} role="alert">
          {message}
        </p>
      ))}
      {saved && <p role="status">{t('botsDigest.settings.saved')}</p>}
      <button type="submit" disabled={saving}>
        {t('botsDigest.settings.save')}
      </button>
    </form>
  );
}

/**
 * The owner's digest settings (#10502), loaded when first opened. They are
 * the owner's own, so anyone with access to the owner may change them.
 */
export function BotsDigestSettings({ owner }: { owner: string }) {
  const { t } = useTranslation();
  const [load, setLoad] = useState<Load>({ kind: 'idle' });

  const open = () => {
    if (load.kind !== 'idle' && load.kind !== 'error') return;
    setLoad({ kind: 'loading' });
    Promise.all([getBotsDigestSettings(owner), getBots()])
      .then(([settings, bots]) => setLoad({ kind: 'ready', settings, bots }))
      .catch(() => setLoad({ kind: 'error' }));
  };

  return (
    <details
      data-testid="bots-digest-settings"
      onToggle={(e) => (e.currentTarget.open ? open() : undefined)}
    >
      <summary>{t('botsDigest.settings.title')}</summary>
      {load.kind === 'loading' && <p>{t('botsDigest.settings.loading')}</p>}
      {load.kind === 'error' && (
        <p role="alert">{t('botsDigest.settings.loadError')}</p>
      )}
      {load.kind === 'ready' && (
        <SettingsForm owner={owner} initial={load.settings} bots={load.bots} />
      )}
    </details>
  );
}

export default BotsDigestSettings;
