import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { Account } from '../types';
import { getAlerts, getDividends, getGroupMovers } from '../api';
import { holdingsFromAccounts } from '../lib/dividends';
import { money, signedPercent } from '../lib/money';
import {
  advanceVisitRecord,
  buildSinceLastVisitDigest,
  dismissVisitRecord,
  moversWindowDays,
  visitDay,
  type SinceLastVisitDigest as Digest,
  type VisitRecord,
} from '../lib/sinceLastVisit';
import { loadJSON, saveJSON } from '../utils/storage';

export const LAST_VISIT_KEY_PREFIX = 'allotmint.lastVisit.';
const MOVERS_FETCH_LIMIT = 10;

/**
 * Record this visit for ``slug`` and return the previous one (epoch ms), or
 * null on a first visit. Storage can be blocked; the digest then just never
 * shows, which is the same as a first visit.
 */
function recordVisit(slug: string, now: number): number | null {
  const key = `${LAST_VISIT_KEY_PREFIX}${slug}`;
  const record = advanceVisitRecord(loadJSON<VisitRecord | null>(key, null), now);
  persistVisit(key, record);
  return record.previous;
}

/** Mark everything up to ``now`` as seen for ``slug`` (the card was dismissed). */
function recordDismissal(slug: string, now: number): void {
  persistVisit(`${LAST_VISIT_KEY_PREFIX}${slug}`, dismissVisitRecord(now));
}

function persistVisit(key: string, record: VisitRecord): void {
  try {
    saveJSON(key, record);
  } catch (err) {
    console.warn('Could not persist last-visit timestamp', err);
  }
}

const ownersFromAccounts = (accounts: Account[]): string[] =>
  Array.from(
    new Set(accounts.map((acct) => acct.owner).filter((o): o is string => Boolean(o)))
  ).sort();

type Props = {
  slug: string;
  /** The loaded group's accounts; null until the portfolio has loaded. */
  accounts: Account[] | null;
};

/**
 * Dismissible "since you were last here" card (#7835). It fetches only once
 * the portfolio has loaded, so it never delays the dashboard's first paint.
 */
export function SinceLastVisitDigest({ slug, accounts }: Props) {
  const { t } = useTranslation();
  const [since, setSince] = useState<number | null>(null);
  const [digest, setDigest] = useState<Digest | null>(null);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    setDigest(null);
    setDismissed(false);
    setSince(slug ? recordVisit(slug, Date.now()) : null);
  }, [slug]);

  const owners = useMemo(() => (accounts ? ownersFromAccounts(accounts) : []), [accounts]);
  const heldTickers = useMemo(
    () => (accounts ? Array.from(holdingsFromAccounts(accounts).keys()) : []),
    [accounts]
  );
  const ready = Boolean(accounts) && since !== null;
  const days = useMemo(
    () => (since === null ? 1 : moversWindowDays(since, Date.now())),
    [since]
  );

  useEffect(() => {
    if (!ready || since === null) return;
    let cancelled = false;
    // Async wrappers turn a synchronous throw into a rejected source rather
    // than an uncaught error, so one bad source never hides the others.
    Promise.allSettled([
      (async () => getGroupMovers(slug, days, MOVERS_FETCH_LIMIT))(),
      (async () => getAlerts())(),
      (async () => getDividends({ start: visitDay(since) }))(),
    ]).then(([movers, alerts, dividends]) => {
      if (cancelled) return;
      const value = <T,>(result: PromiseSettledResult<T>, label: string): T | null => {
        if (result.status === 'fulfilled') return result.value;
        console.warn(`Since-last-visit digest: ${label} unavailable`, result.reason);
        return null;
      };
      setDigest(
        buildSinceLastVisitDigest({
          since,
          movers: value(movers, 'movers'),
          alerts: value(alerts, 'alerts'),
          dividends: value(dividends, 'dividends'),
          owners,
          heldTickers,
        })
      );
    });
    return () => {
      cancelled = true;
    };
  }, [ready, since, slug, days, owners, heldTickers]);

  if (dismissed || since === null || !digest) return null;

  const dismiss = () => {
    recordDismissal(slug, Date.now());
    setDismissed(true);
  };
  const title = t('sinceLastVisit.title', 'Since you were last here');
  const dividendAmounts = Object.entries(digest.dividends?.amounts ?? {})
    .map(([currency, amount]) => money(amount, currency))
    .join(', ');

  return (
    <section
      aria-label={title}
      className="mb-4 rounded p-4 text-sm"
      style={{
        background: 'var(--summary-card-bg)',
        border: '1px solid var(--summary-card-border)',
        color: 'var(--summary-card-value)',
      }}
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-2" style={{ flex: '1 1 16rem', minWidth: 0 }}>
          <h2 className="text-base font-semibold">{title}</h2>
          <p>
            {t('sinceLastVisit.since', 'Changes since {{date}}.', {
              date: new Date(since).toLocaleString(),
            })}
          </p>
          {digest.nothingChanged ? (
            <p>
              {t(
                'sinceLastVisit.nothingChanged',
                'Nothing notable since then: no big movers, alerts or dividends.'
              )}
            </p>
          ) : (
            <ul className="list-disc space-y-1 pl-5">
              <li>
                {digest.movers === null
                  ? t('sinceLastVisit.moversUnavailable', 'Movers are unavailable right now.')
                  : digest.movers.length === 0
                    ? t('sinceLastVisit.noMovers', 'No big movers among your holdings.')
                    : t('sinceLastVisit.movers', 'Biggest movers over the last {{days}} days: {{list}}', {
                        days,
                        list: digest.movers
                          .map((row) => `${row.ticker} ${signedPercent(row.change_pct / 100)}`)
                          .join(', '),
                      })}
              </li>
              <li>
                {digest.alerts === null
                  ? t('sinceLastVisit.alertsUnavailable', 'Alerts are unavailable right now.')
                  : digest.alerts.length === 0
                    ? t('sinceLastVisit.noAlerts', 'No alert thresholds crossed.')
                    : t('sinceLastVisit.alerts', 'Alerts: {{list}}', {
                        list: digest.alerts.map((alert) => alert.message).join('; '),
                      })}
              </li>
              <li>
                {digest.dividends === null
                  ? t('sinceLastVisit.dividendsUnavailable', 'Dividends are unavailable right now.')
                  : digest.dividends.payments === 0
                    ? t('sinceLastVisit.noDividends', 'No dividends paid.')
                    : t('sinceLastVisit.dividends', 'Dividends paid: {{amount}} ({{payments}} payments)', {
                        amount: dividendAmounts,
                        payments: digest.dividends.payments,
                      })}
              </li>
            </ul>
          )}
        </div>
        <button type="button" onClick={dismiss} className="shrink-0">
          {t('sinceLastVisit.dismiss', 'Dismiss')}
        </button>
      </div>
    </section>
  );
}

export default SinceLastVisitDigest;
