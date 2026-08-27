import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  getOwners,
  getUserConfig,
  updateUserConfig,
  getApprovals,
  addApproval,
  removeApproval,
} from '../api';
import type { Approval, OwnerSummary, UserConfig } from '../types';
import { useAuth } from '../AuthContext';
import { findOwnerForUser, sanitizeOwners } from '../utils/owners';

/**
 * Distinguish permission/session failures from generic ones so the approvals
 * error message tells the user something actionable instead of a blanket
 * "Failed to ..." (#5215 -- a 403 here was previously indistinguishable from
 * a network hiccup).
 */
function approvalsErrorMessage(err: unknown, fallback: string): string {
  const status = (err as { status?: number } | null | undefined)?.status;
  if (status === 403) {
    return "You don't have permission to view or manage approvals for this account.";
  }
  if (status === 401) {
    return 'Your session has expired. Sign in again to manage approvals.';
  }
  return fallback;
}

type UserConfigPageProps = {
  selectedOwner?: string;
};

export default function UserConfigPage({ selectedOwner = '' }: UserConfigPageProps) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [owners, setOwners] = useState<OwnerSummary[]>([]);
  const [ownersLoading, setOwnersLoading] = useState(true);
  const [owner, setOwner] = useState('');
  const [cfg, setCfg] = useState<UserConfig>({});
  const [status, setStatus] = useState<string | null>(null);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [newTicker, setNewTicker] = useState('');
  const [newDate, setNewDate] = useState('');
  const [approvalsError, setApprovalsError] = useState<string | null>(null);

  const placeholder =
    'https://www.gravatar.com/avatar/00000000000000000000000000000000?d=mp&f=y&s=192';

  useEffect(() => {
    getOwners()
      .then((os) => setOwners(sanitizeOwners(os)))
      .catch(() => {
        setOwners([]);
      })
      .finally(() => setOwnersLoading(false));
  }, []);

  useEffect(() => {
    if (!owners.length) return;
    setOwner((current) => {
      if (current) return current;
      if (selectedOwner && owners.some((o) => o.owner === selectedOwner)) {
        return selectedOwner;
      }
      return findOwnerForUser(owners, user)?.owner || '';
    });
  }, [owners, user, selectedOwner]);

  useEffect(() => {
    if (owner) {
      getUserConfig(owner)
        .then((res) => {
          const toArrayOrUndefined = (val: unknown): string[] | undefined =>
            Array.isArray(val) ? val : undefined;
          setCfg({
            ...res,
            approval_exempt_tickers: toArrayOrUndefined(
              res.approval_exempt_tickers
            ),
            approval_exempt_types: toArrayOrUndefined(
              res.approval_exempt_types
            ),
          });
        })
        .catch(() => {
          setCfg({});
        });
      getApprovals(owner)
        .then((res) => {
          setApprovals(res.approvals);
          setApprovalsError(null);
        })
        .catch((err) => {
          setApprovals([]);
          setApprovalsError(approvalsErrorMessage(err, 'Failed to load approvals'));
        });
    }
  }, [owner]);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!owner) return;
    setStatus('saving');
    try {
      const payload: any = {
        ...cfg,
        approval_exempt_tickers: cfg.approval_exempt_tickers ?? [],
        approval_exempt_types: cfg.approval_exempt_types ?? null,
      };
      await updateUserConfig(owner, payload);
      setStatus('saved');
    } catch {
      setStatus('error');
    }
  }

  async function add(e: React.FormEvent) {
    e.preventDefault();
    if (!owner || !newTicker || !newDate) return;
    try {
      const res = await addApproval(owner, newTicker, newDate);
      setApprovals(res.approvals);
      setNewTicker('');
      setNewDate('');
      setApprovalsError(null);
    } catch (err) {
      setApprovalsError(approvalsErrorMessage(err, 'Failed to add approval'));
    }
  }

  async function remove(ticker: string) {
    if (!owner) return;
    try {
      const res = await removeApproval(owner, ticker);
      setApprovals(res.approvals);
      setApprovalsError(null);
    } catch (err) {
      setApprovalsError(approvalsErrorMessage(err, 'Failed to remove approval'));
    }
  }

  return (
    <div className="container mx-auto max-w-xl space-y-4 p-4">
      <h1 className="text-2xl md:text-4xl">
        {t('userConfig.title', 'Trading Rules')}
      </h1>
      <p className="text-gray-800 dark:text-gray-200">
        {t(
          'userConfig.subtitle',
          'The compliance rules that govern how this account can trade, and the tickers pre-approved to bypass them.'
        )}
      </p>
      {user && (
        <section className="flex flex-col items-center space-y-4 rounded-lg border p-4">
          <h2 className="text-lg font-semibold">
            {t('userConfig.accountHeading', 'Signed in as')}
          </h2>
          {user.picture ? (
            <img
              src={user.picture}
              alt={user.name || user.email || 'user avatar'}
              width={96}
              height={96}
              className="h-24 w-24 rounded-full"
            />
          ) : (
            <img
              src={placeholder}
              width={96}
              height={96}
              alt="user avatar"
              className="h-24 w-24 rounded-full"
            />
          )}
          {user.name && <div className="text-xl">{user.name}</div>}
          {user.email && (
            <div className="text-gray-800 dark:text-gray-200">{user.email}</div>
          )}
        </section>
      )}
      {ownersLoading ? (
        <p className="text-gray-800 dark:text-gray-200">
          {t('userConfig.loadingOwners', 'Loading owners...')}
        </p>
      ) : owners.length === 0 ? (
        <p className="text-gray-800 dark:text-gray-200">
          {t(
            'userConfig.noOwners',
            'No accounts are available for your account. Contact an administrator if you believe this is an error.'
          )}
        </p>
      ) : (
        <select
          className="w-full border p-2"
          value={owner}
          onChange={(e) => setOwner(e.target.value)}
        >
          <option value="">{t('userConfig.selectOwner', 'Select owner')}</option>
          {owners.map((o) => (
            <option key={o.owner} value={o.owner}>
              {o.full_name?.trim() ? o.full_name : o.owner}
            </option>
          ))}
        </select>
      )}
      {!owner && !ownersLoading && owners.length > 0 && (
        <p role="status" className="text-gray-800 dark:text-gray-200">
          {t(
            'userConfig.selectOwnerPrompt',
            'Select an account holder to view their settings.'
          )}
        </p>
      )}
      {owner && (
        <>
          <form onSubmit={save} className="space-y-2">
            <div>
              <label htmlFor="userConfig-holdDays" className="block text-sm">
                {t('userConfig.holdDays', 'Min Hold Days (days)')}
              </label>
              <p
                id="userConfig-holdDays-help"
                className="text-xs text-gray-600 dark:text-gray-400"
              >
                {t(
                  'userConfig.holdDaysHelp',
                  'The number of days a newly bought position must be held before it can be sold.'
                )}
              </p>
              <input
                id="userConfig-holdDays"
                type="number"
                className="w-full border p-1"
                aria-describedby="userConfig-holdDays-help"
                value={cfg.hold_days_min ?? ''}
                onChange={(e) =>
                  setCfg({
                    ...cfg,
                    hold_days_min: e.target.value
                      ? Number(e.target.value)
                      : undefined,
                  })
                }
              />
            </div>
            <div>
              <label htmlFor="userConfig-maxTrades" className="block text-sm">
                {t('userConfig.maxTrades', 'Max Trades / Month (trades)')}
              </label>
              <p
                id="userConfig-maxTrades-help"
                className="text-xs text-gray-600 dark:text-gray-400"
              >
                {t(
                  'userConfig.maxTradesHelp',
                  'The number of trades made in the current calendar month; resets on the 1st, not a rolling 30-day window. Exceeding it raises a compliance warning; it does not block trading.'
                )}
              </p>
              <input
                id="userConfig-maxTrades"
                type="number"
                className="w-full border p-1"
                aria-describedby="userConfig-maxTrades-help"
                value={cfg.max_trades_per_month ?? ''}
                onChange={(e) =>
                  setCfg({
                    ...cfg,
                    max_trades_per_month: e.target.value
                      ? Number(e.target.value)
                      : undefined,
                  })
                }
              />
            </div>
            <div>
              <label htmlFor="userConfig-exemptTickers" className="block text-sm">
                {t(
                  'userConfig.exemptTickers',
                  'Approval Exempt Tickers (comma-separated)'
                )}
              </label>
              <p
                id="userConfig-exemptTickers-help"
                className="text-xs text-gray-600 dark:text-gray-400"
              >
                {t(
                  'userConfig.exemptTickersHelp',
                  'Tickers listed here can be traded without going through the approvals process below.'
                )}
              </p>
              <input
                id="userConfig-exemptTickers"
                type="text"
                className="w-full border p-1"
                aria-describedby="userConfig-exemptTickers-help"
                value={(Array.isArray(cfg.approval_exempt_tickers)
                  ? cfg.approval_exempt_tickers
                  : []
                ).join(',')}
                onChange={(e) =>
                  setCfg({
                    ...cfg,
                    approval_exempt_tickers: e.target.value
                      ? e.target.value.split(/,\s*/)
                      : [],
                  })
                }
              />
            </div>
            <div>
              <label htmlFor="userConfig-exemptTypes" className="block text-sm">
                {t(
                  'userConfig.exemptTypes',
                  'Approval Exempt Types (comma-separated)'
                )}
              </label>
              <p
                id="userConfig-exemptTypes-help"
                className="text-xs text-gray-600 dark:text-gray-400"
              >
                {t(
                  'userConfig.exemptTypesHelp',
                  "Instrument types listed here (e.g. ETF, Fund) skip the approval requirement -- except commodity ETFs, which don't get the type exemption. List them individually in Approval Exempt Tickers above if you want them exempt."
                )}
              </p>
              <input
                id="userConfig-exemptTypes"
                type="text"
                className="w-full border p-1"
                aria-describedby="userConfig-exemptTypes-help"
                value={(Array.isArray(cfg.approval_exempt_types)
                  ? cfg.approval_exempt_types
                  : []
                ).join(',')}
                onChange={(e) =>
                  setCfg({
                    ...cfg,
                    approval_exempt_types: e.target.value
                      ? e.target.value.split(/,\s*/)
                      : [],
                  })
                }
              />
            </div>
            <button
              type="submit"
              className="bg-blue-500 px-4 py-2 text-white"
              disabled={status === 'saving'}
            >
              {status === 'saving'
                ? t('userConfig.saving', 'Saving...')
                : t('userConfig.save', 'Save')}
            </button>
            {status === 'saved' && (
              <span>{t('userConfig.saved', 'Saved')}</span>
            )}
            {status === 'error' && (
              <span className="text-red-500">
                {t('userConfig.error', 'Error')}
              </span>
            )}
          </form>
          <div className="space-y-2 pt-4">
            <h2 className="text-xl">
              {t('userConfig.approvals', 'Approvals')}
            </h2>
            <p className="text-xs text-gray-600 dark:text-gray-400">
              {t(
                'userConfig.approvalsHelp',
                "Tickers explicitly cleared to trade outside the exemptions above. Each approval is only valid for the deployment's configured approval window in trading days, starting from the date shown -- if no window is configured, it is valid only on the day it's granted."
              )}
            </p>
            <table className="w-full border">
              <thead>
                <tr>
                  <th className="border px-2 text-left">Ticker</th>
                  <th className="border px-2 text-left">Date</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {approvals.map((a, index) => (
                  <tr key={`${a.ticker}-${index}`}>
                    <td className="border px-2">{a.ticker}</td>
                    <td className="border px-2">{a.approved_on}</td>
                    <td className="border px-2 text-right">
                      <button
                        type="button"
                        className="text-red-500"
                        onClick={() => remove(a.ticker)}
                      >
                        {t('userConfig.remove', 'Remove')}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {approvalsError && (
              <div className="text-red-500">{approvalsError}</div>
            )}
            <form
              onSubmit={add}
              className="flex flex-wrap space-x-2 md:flex-nowrap"
            >
              <input
                type="text"
                className="flex-1 border p-1"
                placeholder="Ticker"
                aria-label={t('userConfig.newTickerLabel', 'Ticker')}
                value={newTicker}
                onChange={(e) => setNewTicker(e.target.value)}
              />
              <input
                type="date"
                className="border p-1"
                aria-label={t('userConfig.newDateLabel', 'Approval date')}
                value={newDate}
                onChange={(e) => setNewDate(e.target.value)}
              />
              <button type="submit" className="bg-blue-500 px-2 text-white">
                {t('userConfig.add', 'Add')}
              </button>
            </form>
          </div>
        </>
      )}
    </div>
  );
}
