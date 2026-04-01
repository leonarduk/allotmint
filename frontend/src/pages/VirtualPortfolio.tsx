import { FormEvent, useEffect, useMemo, useState } from "react";
import { logAnalyticsEvent } from "@/api";

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

const STORAGE_KEY = "familyManualPortfolio.v1";

function createId(): string {
  try {
    if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
      return crypto.randomUUID();
    }
  } catch {
    // Fallback below.
  }

  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function createHolding(): ManualHolding {
  return {
    id: createId(),
    ticker: "",
    totalValue: "",
    units: "",
    price: "",
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
  if (value.trim() === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function isManualHolding(value: unknown): value is ManualHolding {
  const row = value as ManualHolding | null;
  return (
    typeof row?.id === "string"
    && typeof row.ticker === "string"
    && typeof row.totalValue === "string"
    && typeof row.units === "string"
    && typeof row.price === "string"
  );
}

function readInitialAccounts(): ManualAccount[] {
  if (typeof window === "undefined") return [];
  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (!raw) return [];

  try {
    const parsed = JSON.parse(raw) as ManualAccount[];
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((account) => typeof account?.id === "string" && typeof account?.name === "string")
      .map((account) => {
        const sanitizedHoldings = Array.isArray(account.holdings)
          ? account.holdings.filter((holding) => isManualHolding(holding))
          : [];

        return {
          ...account,
          holdings: sanitizedHoldings,
        };
      });
  } catch {
    return [];
  }
}

export function VirtualPortfolio() {
  const [accounts, setAccounts] = useState<ManualAccount[]>(readInitialAccounts);
  const [newAccountName, setNewAccountName] = useState("");
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  const canAddAccount = newAccountName.trim().length > 0;

  useEffect(() => {
    const maybePromise = logAnalyticsEvent({
      source: "virtual_portfolio",
      event: "view",
      metadata: { storage_mode: "local" },
    });
    void maybePromise?.catch?.(() => undefined);
  }, []);

  const saveAccounts = (next: ManualAccount[]) => {
    const previous = accounts;
    setAccounts(next);

    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      setStatusMessage(null);
    } catch {
      setAccounts(previous);
      setStatusMessage("Changes were not saved in this browser. Try freeing local storage space.");
    }
  };

  const addAccount = (event?: FormEvent) => {
    event?.preventDefault();
    const trimmed = newAccountName.trim();
    if (!trimmed) {
      setStatusMessage("Enter an account name before adding it.");
      return;
    }

    const isDuplicateName = accounts.some(
      (account) => account.name.trim().toLowerCase() === trimmed.toLowerCase(),
    );
    if (isDuplicateName) {
      setStatusMessage("Use a unique account name.");
      return;
    }

    saveAccounts([...accounts, createAccount(trimmed)]);
    setNewAccountName("");
  };

  const deleteAccount = (accountId: string) => {
    saveAccounts(accounts.filter((account) => account.id !== accountId));
  };

  const updateAccountName = (accountId: string, name: string) => {
    const trimmed = name.trim();
    if (!trimmed) {
      setStatusMessage("Account name cannot be empty.");
      return;
    }

    const isDuplicateName = accounts.some(
      (account) => account.id !== accountId
        && account.name.trim().toLowerCase() === trimmed.toLowerCase()
    );
    if (isDuplicateName) {
      setStatusMessage("Account names must stay unique.");
      return;
    }

    saveAccounts(
      accounts.map((account) => (account.id === accountId ? { ...account, name: trimmed } : account)),
    );
  };

  const addHolding = (accountId: string) => {
    saveAccounts(
      accounts.map((account) =>
        account.id === accountId
          ? { ...account, holdings: [...account.holdings, createHolding()] }
          : account,
      ),
    );
  };

  const removeHolding = (accountId: string, holdingId: string) => {
    const account = accounts.find((entry) => entry.id === accountId);
    if (!account) return;

    const nextHoldings = account.holdings.filter((holding) => holding.id !== holdingId);
    if (nextHoldings.length === 0) {
      setStatusMessage("Each account must keep at least one holding row.");
      return;
    }

    saveAccounts(
      accounts.map((entry) =>
        entry.id === accountId
          ? { ...entry, holdings: nextHoldings }
          : entry,
      ),
    );
  };

  const updateHolding = (
    accountId: string,
    holdingId: string,
    field: keyof Omit<ManualHolding, "id">,
    value: string,
  ) => {
    saveAccounts(
      accounts.map((account) => {
        if (account.id !== accountId) return account;
        return {
          ...account,
          holdings: account.holdings.map((holding) =>
            holding.id === holdingId ? { ...holding, [field]: value } : holding,
          ),
        };
      }),
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
    [accounts],
  );

  return (
    <div className="container mx-auto max-w-5xl space-y-6 p-4">
      <header>
        <h1 className="text-2xl font-semibold md:text-4xl">Family Manual Portfolio Setup</h1>
        <p className="mt-2 text-sm text-slate-600">
          Add accounts and holdings manually. Entries are saved in this browser and survive page
          refresh.
        </p>
      </header>

      {statusMessage && (
        <p className="rounded border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-800">
          {statusMessage}
        </p>
      )}

      <form className="rounded border border-slate-200 p-4" onSubmit={addAccount}>
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
            No accounts yet. Add at least two accounts to complete the initial setup.
          </p>
        )}
        {accounts.map((account) => (
          <article key={account.id} className="rounded border border-slate-200 p-4">
            <div className="mb-3 flex items-center justify-between gap-3">
              <input
                className="w-full rounded border border-slate-300 px-3 py-2"
                type="text"
                value={account.name}
                onChange={(e) => updateAccountName(account.id, e.target.value)}
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
                    <th className="px-2 py-2">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {account.holdings.map((holding) => (
                    <tr key={holding.id} className="border-b border-slate-100 align-top">
                      <td className="px-2 py-2">
                        <input
                          className="w-full rounded border border-slate-300 px-2 py-1"
                          type="text"
                          value={holding.ticker}
                          onChange={(e) =>
                            updateHolding(account.id, holding.id, "ticker", e.target.value)
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
                            updateHolding(account.id, holding.id, "totalValue", e.target.value)
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
                            updateHolding(account.id, holding.id, "units", e.target.value)
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
                            updateHolding(account.id, holding.id, "price", e.target.value)
                          }
                          placeholder="150"
                        />
                      </td>
                      <td className="px-2 py-2">
                        <button
                          type="button"
                          className="rounded border border-slate-300 px-2 py-1"
                          onClick={() => removeHolding(account.id, holding.id)}
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
        <summary className="cursor-pointer text-sm font-medium">Preview saved payload</summary>
        <pre className="mt-2 overflow-x-auto rounded bg-slate-50 p-3 text-xs">
          {JSON.stringify({ accounts: normalizedPreview }, null, 2)}
        </pre>
      </details>
    </div>
  );
}

export default VirtualPortfolio;
