import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  createAccount as createSavedAccount,
  createManualHolding,
  logAnalyticsEvent,
} from '@/api';

interface ManualHolding {
  id: string;
  ticker: string;
  totalValue: string;
  units: string;
  price: string;
}

interface ManualAccount {
  id: string;
  name: string;
  holdings: ManualHolding[];
}

const STORAGE_KEY = 'familyManualPortfolio.v1';

function createId(): string {
  // Prefer built-in cryptographically secure UUID when available (all modern browsers + HTTPS).
  try {
    if (
      typeof crypto !== 'undefined' &&
      typeof crypto.randomUUID === 'function'
    ) {
      return crypto.randomUUID();
    }
  } catch {
    // Fallback below.
  }

  // crypto.randomUUID unavailable: derive a UUID v4 from secure random bytes.
  // This path is only reached on very old browsers or non-secure contexts.
  try {
    const globalCrypto: Crypto | undefined =
      typeof crypto !== 'undefined'
        ? crypto
        : typeof window !== 'undefined'
          ? (window as unknown as { crypto?: Crypto }).crypto
          : undefined;

    if (globalCrypto && typeof globalCrypto.getRandomValues === 'function') {
      const bytes = new Uint8Array(16);
      globalCrypto.getRandomValues(bytes);
      // Set version (4) and variant bits per RFC 4122.
      bytes[6] = (bytes[6] & 0x0f) | 0x40;
      bytes[8] = (bytes[8] & 0x3f) | 0x80;
      const toHex = (n: number) => n.toString(16).padStart(2, '0');
      const b = Array.from(bytes, toHex).join('');
      return [
        b.slice(0, 8),
        b.slice(8, 12),
        b.slice(12, 16),
        b.slice(16, 20),
        b.slice(20),
      ].join('-');
    }
  } catch {
    // Last-resort fallback below.
  }

  // Absolute last resort: time + performance counter (no Math.random).
  // Uniqueness is best-effort only; this path should never be reached in production.
  // NOTE: result is not a valid UUID — do not rely on UUID format here.
  return `${Date.now().toString(16)}-${(typeof performance !== 'undefined' ? performance.now() : 0).toString(16).replace('.', '')}`;
}

function createHolding(): ManualHolding {
  return {
    id: createId(),
    ticker: '',
    totalValue: '',
    units: '',
    price: '',
  };
}

function createAccount(name: string): ManualAccount {
  return {
    id: createId(),
    name,
    holdings: [createHolding()],
  };
}

function parseNumber(value: string): number | null {
  if (value.trim() === '') return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function isManualHolding(value: unknown): value is ManualHolding {
  const row = value as ManualHolding | null;
  return (
    typeof row?.id === 'string' &&
    typeof row.ticker === 'string' &&
    typeof row.totalValue === 'string' &&
    typeof row.units === 'string' &&
    typeof row.price === 'string'
  );
}

function readInitialAccounts(): ManualAccount[] {
  if (typeof window === 'undefined') return [];
  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (!raw) return [];

  try {
    const parsed = JSON.parse(raw) as ManualAccount[];
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter(
        (account) =>
          typeof account?.id === 'string' && typeof account?.name === 'string'
      )
      .map((account) => {
        const sanitizedHoldings = Array.isArray(account.holdings)
          ? account.holdings.filter((holding) => isManualHolding(holding))
          : [];

        return {
          ...account,
          // Ensure every account has at least one holding row after hydration.
          holdings:
            sanitizedHoldings.length > 0
              ? sanitizedHoldings
              : [createHolding()],
        };
      });
  } catch {
    return [];
  }
}

interface VirtualPortfolioProps {
  owner?: string;
}

function savedAccountType(name: string): string {
  return name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

export function VirtualPortfolio({ owner = '' }: VirtualPortfolioProps) {
  const navigate = useNavigate();
  const [accounts, setAccounts] =
    useState<ManualAccount[]>(readInitialAccounts);
  const [newAccountName, setNewAccountName] = useState('');
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [showCommitConfirmation, setShowCommitConfirmation] = useState(false);
  const [isCommitting, setIsCommitting] = useState(false);
  // draftNames holds the in-progress value for account name inputs, decoupled from
  // the persisted accounts state. This prevents the input from snapping back to the
  // last-saved value while the user is mid-edit (e.g. clearing the field to retype).
  const [draftNames, setDraftNames] = useState<Record<string, string>>({});

  const canAddAccount = newAccountName.trim().length > 0;

  useEffect(() => {
    const maybePromise = logAnalyticsEvent({
      source: 'virtual_portfolio',
      event: 'view',
      metadata: { storage_mode: 'local' },
    });
    void maybePromise?.catch?.(() => undefined);
  }, []);

  /**
   * Persist `next` to both React state and localStorage.
   * Returns true on success, false if localStorage threw (state is rolled back).
   */
  const saveAccounts = (next: ManualAccount[]): boolean => {
    const previous = accounts;
    setAccounts(next);

    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      setStatusMessage(null);
      return true;
    } catch {
      setAccounts(previous);
      setStatusMessage(
        'Changes were not saved in this browser. Try freeing local storage space.'
      );
      return false;
    }
  };

  const addAccount = (event?: FormEvent) => {
    event?.preventDefault();
    const trimmed = newAccountName.trim();
    if (!trimmed) {
      setStatusMessage('Enter an account name before adding it.');
      return;
    }

    const isDuplicateName = accounts.some(
      (account) => account.name.trim().toLowerCase() === trimmed.toLowerCase()
    );
    if (isDuplicateName) {
      setStatusMessage('Use a unique account name.');
      return;
    }

    saveAccounts([...accounts, createAccount(trimmed)]);
    setNewAccountName('');
  };

  const deleteAccount = (accountId: string) => {
    saveAccounts(accounts.filter((account) => account.id !== accountId));
    setDraftNames((prev) => {
      const next = { ...prev };
      delete next[accountId];
      return next;
    });
  };

  // onChange: update draft only — no validation, no persistence.
  const handleAccountNameChange = (accountId: string, value: string) => {
    setDraftNames((prev) => ({ ...prev, [accountId]: value }));
    // Clear any lingering status message so stale warnings don't confuse the user.
    setStatusMessage(null);
  };

  // onBlur: validate the draft and persist if valid, otherwise revert the draft.
  const commitAccountName = (accountId: string) => {
    const draft = draftNames[accountId];
    // No draft means the value hasn't changed since last persist — nothing to do.
    if (draft === undefined) return;

    const trimmed = draft.trim();
    if (!trimmed) {
      setStatusMessage('Account name cannot be empty.');
      // Revert draft to last-saved name so the input shows the correct value.
      const saved = accounts.find((a) => a.id === accountId)?.name ?? '';
      setDraftNames((prev) => ({ ...prev, [accountId]: saved }));
      return;
    }

    const isDuplicateName = accounts.some(
      (account) =>
        account.id !== accountId &&
        account.name.trim().toLowerCase() === trimmed.toLowerCase()
    );
    if (isDuplicateName) {
      setStatusMessage('Account names must stay unique.');
      const saved = accounts.find((a) => a.id === accountId)?.name ?? '';
      setDraftNames((prev) => ({ ...prev, [accountId]: saved }));
      return;
    }

    // Attempt to persist. Only clear the draft if the write succeeded — if localStorage
    // threw, the draft remains so the user can retry by re-focusing and blurring again.
    const saved = saveAccounts(
      accounts.map((account) =>
        account.id === accountId ? { ...account, name: trimmed } : account
      )
    );
    if (saved) {
      setDraftNames((prev) => {
        const next = { ...prev };
        delete next[accountId];
        return next;
      });
    }
  };

  const addHolding = (accountId: string) => {
    saveAccounts(
      accounts.map((account) =>
        account.id === accountId
          ? { ...account, holdings: [...account.holdings, createHolding()] }
          : account
      )
    );
  };

  const removeHolding = (accountId: string, holdingId: string) => {
    const account = accounts.find((entry) => entry.id === accountId);
    if (!account) return;

    const nextHoldings = account.holdings.filter(
      (holding) => holding.id !== holdingId
    );
    // Button is disabled when holdings.length <= 1 so this guard is a safety net only.
    if (nextHoldings.length === 0) return;

    saveAccounts(
      accounts.map((entry) =>
        entry.id === accountId ? { ...entry, holdings: nextHoldings } : entry
      )
    );
  };

  const updateHolding = (
    accountId: string,
    holdingId: string,
    field: keyof Omit<ManualHolding, 'id'>,
    value: string
  ) => {
    saveAccounts(
      accounts.map((account) => {
        if (account.id !== accountId) return account;
        return {
          ...account,
          holdings: account.holdings.map((holding) =>
            holding.id === holdingId ? { ...holding, [field]: value } : holding
          ),
        };
      })
    );
  };

  const normalizedPreview = useMemo(
    () =>
      accounts.map((account) => ({
        account_name: account.name,
        holdings: account.holdings
          .map((holding) => {
            const totalValue = parseNumber(holding.totalValue);
            const units = parseNumber(holding.units);
            const price = parseNumber(holding.price);
            const ticker = holding.ticker.trim().toUpperCase();
            if (!ticker) return null;

            // totalValue takes precedence over units+price when both are provided.
            if (totalValue != null) {
              return { ticker, total_value: totalValue };
            }

            if (units != null && price != null) {
              return { ticker, units, price };
            }

            return null;
          })
          .filter((holding) => holding != null),
      })),
    [accounts]
  );

  const committableAccounts = useMemo(
    () => normalizedPreview.filter((account) => account.holdings.length > 0),
    [normalizedPreview]
  );

  const commitToPortfolio = async () => {
    if (!owner || committableAccounts.length === 0) return;
    setIsCommitting(true);
    setStatusMessage(null);
    try {
      for (const account of committableAccounts) {
        const created = await createSavedAccount({
          owner,
          account_type: savedAccountType(account.account_name) || "draft-account",
          currency: 'GBP',
        });
        for (const holding of account.holdings) {
          await createManualHolding({
            owner,
            account: created.account,
            ticker: holding.ticker,
            ...(holding.total_value != null
              ? { value_gbp: holding.total_value }
              : { units: holding.units, price_gbp: holding.price }),
          });
        }
      }
      setShowCommitConfirmation(false);
      navigate('/portfolio');
    } catch {
      setStatusMessage(
        'The draft could not be fully committed. Your local draft is unchanged; check your saved portfolio before trying again.'
      );
    } finally {
      setIsCommitting(false);
    }
  };

  return (
    <div className="container mx-auto max-w-5xl space-y-6 p-4">
      <header>
        <p className="mb-2 inline-flex rounded-full bg-amber-100 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-amber-900">
          Local draft
        </p>
        <h1 className="text-2xl font-semibold md:text-4xl">
          Family Manual Portfolio Draft
        </h1>
        <p className="mt-2 text-sm text-slate-600">
          Explore a possible family portfolio without changing your saved
          portfolio. This draft is stored only in this browser and is not saved
          to your AllotMint account.
        </p>
      </header>

      <aside
        className="rounded border border-amber-300 bg-amber-50 p-4 text-sm text-amber-950"
        aria-labelledby="local-draft-notice"
      >
        <h2 id="local-draft-notice" className="font-semibold">
          This draft stays separate
        </h2>
        <p className="mt-1">
          Draft accounts and holdings cannot currently be transferred
          automatically. To keep them in your account, open your saved portfolio
          and use Add account, Add position, or Import CSV.
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          <a
            href="/portfolio"
            className="inline-flex rounded bg-slate-900 px-4 py-2 font-medium text-white hover:bg-slate-700"
          >
            Open saved portfolio
          </a>
          {committableAccounts.length > 0 && (
            <button
              type="button"
              disabled={!owner}
              title={
                !owner
                  ? 'Select a portfolio owner before committing this draft.'
                  : undefined
              }
              className="rounded border border-amber-700 px-4 py-2 font-medium disabled:cursor-not-allowed disabled:opacity-50"
              onClick={() => setShowCommitConfirmation(true)}
            >
              Commit to portfolio
            </button>
          )}
        </div>
      </aside>

      {showCommitConfirmation && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="commit-draft-title"
          className="rounded border border-slate-300 bg-white p-4 shadow-lg"
        >
          <h2 id="commit-draft-title" className="text-lg font-semibold">
            Commit this draft?
          </h2>
          <p className="mt-2 text-sm text-slate-600">
            This will copy {committableAccounts.length} draft{' '}
            {committableAccounts.length === 1 ? 'account' : 'accounts'} and
            their holdings into your saved portfolio. Your browser-local draft
            will be kept unchanged.
          </p>
          <div className="mt-4 flex gap-2">
            <button
              type="button"
              disabled={isCommitting}
              className="rounded bg-slate-900 px-4 py-2 text-white disabled:opacity-50"
              onClick={() => void commitToPortfolio()}
            >
              {isCommitting ? 'Committing…' : 'Confirm commit'}
            </button>
            <button
              type="button"
              disabled={isCommitting}
              className="rounded border border-slate-300 px-4 py-2 disabled:opacity-50"
              onClick={() => setShowCommitConfirmation(false)}
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {statusMessage && (
        <p className="rounded border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-800">
          {statusMessage}
        </p>
      )}

      <form
        className="rounded border border-slate-200 p-4"
        onSubmit={addAccount}
      >
        <h2 className="text-lg font-medium">Add account</h2>
        <div className="mt-3 flex flex-col gap-2 sm:flex-row">
          <input
            className="w-full rounded border border-slate-300 px-3 py-2"
            type="text"
            placeholder="Account name (e.g. ISA, Pension, Brokerage)"
            value={newAccountName}
            onChange={(e) => setNewAccountName(e.target.value)}
          />
          <button
            type="submit"
            className="rounded bg-slate-900 px-4 py-2 text-white disabled:cursor-not-allowed disabled:opacity-50"
            disabled={!canAddAccount}
          >
            Add account
          </button>
        </div>
      </form>

      <section className="space-y-4">
        {accounts.length === 0 && (
          <p className="rounded border border-dashed border-slate-300 p-4 text-sm text-slate-600">
            No accounts yet. Add at least two accounts to complete the initial
            setup.
          </p>
        )}
        {accounts.map((account) => (
          <article
            key={account.id}
            className="rounded border border-slate-200 p-4"
          >
            <div className="mb-3 flex items-center justify-between gap-3">
              <input
                className="w-full rounded border border-slate-300 px-3 py-2"
                type="text"
                // Use draft value while editing; fall back to persisted name otherwise.
                value={draftNames[account.id] ?? account.name}
                onChange={(e) =>
                  handleAccountNameChange(account.id, e.target.value)
                }
                onBlur={() => commitAccountName(account.id)}
                aria-label="Account name"
              />
              <button
                type="button"
                className="rounded border border-red-300 px-3 py-2 text-sm text-red-600"
                onClick={() => deleteAccount(account.id)}
              >
                Remove account
              </button>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full min-w-[680px] border-collapse text-sm">
                <thead>
                  <tr className="border-b border-slate-200 text-left">
                    <th className="px-2 py-2">Ticker</th>
                    <th className="px-2 py-2">Total value</th>
                    <th className="px-2 py-2">Units</th>
                    <th className="px-2 py-2">Price</th>
                    <th className="px-2 py-2" aria-label="Actions">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {account.holdings.map((holding) => (
                    <tr
                      key={holding.id}
                      className="border-b border-slate-100 align-top"
                    >
                      <td className="px-2 py-2">
                        <input
                          className="w-full rounded border border-slate-300 px-2 py-1"
                          type="text"
                          value={holding.ticker}
                          onChange={(e) =>
                            updateHolding(
                              account.id,
                              holding.id,
                              'ticker',
                              e.target.value
                            )
                          }
                          placeholder="AAPL"
                        />
                      </td>
                      <td className="px-2 py-2">
                        <input
                          className="w-full rounded border border-slate-300 px-2 py-1"
                          type="number"
                          step="any"
                          value={holding.totalValue}
                          onChange={(e) =>
                            updateHolding(
                              account.id,
                              holding.id,
                              'totalValue',
                              e.target.value
                            )
                          }
                          placeholder="25000"
                        />
                      </td>
                      <td className="px-2 py-2">
                        <input
                          className="w-full rounded border border-slate-300 px-2 py-1"
                          type="number"
                          step="any"
                          value={holding.units}
                          onChange={(e) =>
                            updateHolding(
                              account.id,
                              holding.id,
                              'units',
                              e.target.value
                            )
                          }
                          placeholder="10"
                        />
                      </td>
                      <td className="px-2 py-2">
                        <input
                          className="w-full rounded border border-slate-300 px-2 py-1"
                          type="number"
                          step="any"
                          value={holding.price}
                          onChange={(e) =>
                            updateHolding(
                              account.id,
                              holding.id,
                              'price',
                              e.target.value
                            )
                          }
                          placeholder="150"
                        />
                      </td>
                      <td className="px-2 py-2">
                        <button
                          type="button"
                          className="rounded border border-slate-300 px-2 py-1 disabled:cursor-not-allowed disabled:opacity-40"
                          disabled={account.holdings.length <= 1}
                          onClick={() => removeHolding(account.id, holding.id)}
                          aria-label="Remove holding"
                        >
                          Remove
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <button
              type="button"
              className="mt-3 rounded border border-slate-300 px-3 py-2 text-sm"
              onClick={() => addHolding(account.id)}
            >
              Add holding
            </button>
          </article>
        ))}
      </section>

      <details className="rounded border border-slate-200 p-3">
        <summary className="cursor-pointer text-sm font-medium">
          Preview saved payload
        </summary>
        <pre className="mt-2 overflow-x-auto rounded bg-slate-50 p-3 text-xs">
          {JSON.stringify({ accounts: normalizedPreview }, null, 2)}
        </pre>
      </details>
    </div>
  );
}

export default VirtualPortfolio;
