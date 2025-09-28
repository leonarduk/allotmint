import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  getVirtualPortfolios,
  getVirtualPortfolio,
  createVirtualPortfolio,
  updateVirtualPortfolio,
  deleteVirtualPortfolio,
  getOwners,
  logAnalyticsEvent,
} from "../api";
import errorToast from "../utils/errorToast";
import type {
  SyntheticHolding,
  VirtualPortfolio as VP,
  OwnerSummary,
  VirtualPortfolioAnalyticsEvent,
} from "../types";
import {
  sanitizeOwners,
  createOwnerDisplayLookup,
  getOwnerDisplayName,
} from "../utils/owners";

const MAX_INITIAL_LOAD_ATTEMPTS = 3;
const INITIAL_RETRY_BASE_DELAY_MS = 500;
const INITIAL_RETRY_MAX_DELAY_MS = 2000;

export function VirtualPortfolio() {
  const [portfolios, setPortfolios] = useState<VP[]>([]);
  const [owners, setOwners] = useState<OwnerSummary[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [name, setName] = useState("");
  const [accounts, setAccounts] = useState<string[]>([]);
  const [holdings, setHoldings] = useState<SyntheticHolding[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [hasLoadedInitialData, setHasLoadedInitialData] = useState(false);
  const isMountedRef = useRef(true);
  const ownerLookup = useMemo(
    () => createOwnerDisplayLookup(owners),
    [owners],
  );

  const track = useCallback(
    (
      event: VirtualPortfolioAnalyticsEvent,
      metadata?: Record<string, unknown>,
    ) => {
      logAnalyticsEvent({
        source: "virtual_portfolio",
        event,
        metadata,
      }).catch(() => undefined);
    },
    [],
  );

  useEffect(() => {
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  const loadInitialData = useCallback(async () => {
    if (!isMountedRef.current) return;

    setLoading(true);
    setMessage(null);
    setError(null);

    for (let attempt = 0; attempt < MAX_INITIAL_LOAD_ATTEMPTS; attempt += 1) {
      try {
        const [ps, os] = await Promise.all([
          getVirtualPortfolios(),
          getOwners(),
        ]);

        if (!isMountedRef.current) {
          return;
        }

        setPortfolios(ps);
        setOwners(sanitizeOwners(os));
        setHasLoadedInitialData(true);
        track("view", { portfolio_count: ps.length });
        break;
      } catch (e) {
        const err = e instanceof Error ? e : new Error(String(e));

        if (!isMountedRef.current) {
          return;
        }

        const isFinalAttempt = attempt === MAX_INITIAL_LOAD_ATTEMPTS - 1;
        if (isFinalAttempt) {
          setError(
            navigator.onLine
              ? "Unable to load virtual portfolios. Please try again."
              : "You appear to be offline.",
          );
          setLoading(false);
          errorToast(err);
          return;
        }

        const delay = Math.min(
          INITIAL_RETRY_BASE_DELAY_MS * 2 ** attempt,
          INITIAL_RETRY_MAX_DELAY_MS,
        );

        if (delay > 0) {
          await new Promise<void>((resolve) => setTimeout(resolve, delay));
          if (!isMountedRef.current) {
            return;
          }
        }
      }
    }

    if (!isMountedRef.current) {
      return;
    }

    setLoading(false);
  }, [track]);

  useEffect(() => {
    loadInitialData();
  }, [loadInitialData]);

  const handleInitialRetry = useCallback(() => {
    if (loading) return;
    loadInitialData();
  }, [loadInitialData, loading]);

  async function load(id: number) {
    try {
      const vp = await getVirtualPortfolio(id);
      setSelected(id);
      setName(vp.name);
      setAccounts(vp.accounts);
      setHoldings(vp.holdings || []);
      track("select", { portfolio_id: id });
    } catch (e) {
      const err = e instanceof Error ? e.message : String(e);
      setError(err);
      errorToast(e);
    }
  }

  function toggleAccount(account: string) {
    setAccounts((prev) =>
      prev.includes(account)
        ? prev.filter((a) => a !== account)
        : [...prev, account],
    );
  }

  function updateHolding(
    idx: number,
    field: keyof SyntheticHolding,
    value: string | number | undefined,
  ) {
    setHoldings((prev) =>
      prev.map((h, i) => (i === idx ? { ...h, [field]: value } : h)),
    );
  }

  function addHolding() {
    setHoldings((prev) => [...prev, { ticker: "", units: 0, price: undefined, purchase_date: "" }]);
  }

  function removeHolding(idx: number) {
    setHoldings((prev) => prev.filter((_, i) => i !== idx));
  }

  async function handleSave() {
    setMessage(null);
    setError(null);
    const payload: VP = { name, accounts, holdings };
    try {
      if (selected != null) {
        await updateVirtualPortfolio(selected, payload);
        track("update", { portfolio_id: selected, holding_count: holdings.length });
      } else {
        const created = await createVirtualPortfolio(payload);
        setSelected(created.id ?? null);
        track("create", {
          portfolio_id: created.id ?? null,
          holding_count: holdings.length,
        });
      }
      setMessage("Saved");
      setPortfolios(await getVirtualPortfolios());
    } catch (e) {
      const err = e instanceof Error ? e.message : String(e);
      setError(err);
      errorToast(e);
    }
  }

  async function handleDelete() {
    if (selected == null) return;
    try {
      await deleteVirtualPortfolio(selected);
      track("delete", { portfolio_id: selected });
      setSelected(null);
      setName("");
      setAccounts([]);
      setHoldings([]);
      setPortfolios(await getVirtualPortfolios());
    } catch (e) {
      const err = e instanceof Error ? e.message : String(e);
      setError(err);
      errorToast(e);
    }
  }

  const isInitialLoading = !hasLoadedInitialData;

  return (
    <div className="container mx-auto p-4">
      <h1 className="mb-4 text-2xl md:text-4xl">Virtual Portfolios</h1>

      {isInitialLoading && <p>Loading...</p>}
      {error && (
        <div className="mb-2">
          <p className="text-red-500">{error}</p>
          {!hasLoadedInitialData && (
            <button
              type="button"
              onClick={handleInitialRetry}
              disabled={loading}
              className="mt-2 rounded border border-red-300 px-3 py-1 text-sm text-red-600 transition disabled:opacity-50"
            >
              Retry
            </button>
          )}
        </div>
      )}
      {message && <p className="text-green-600">{message}</p>}

      <div className="mb-4">
        <label>
          Select
          <select
            value={selected ?? ""}
            onChange={(e) => {
              const id = e.target.value ? Number(e.target.value) : null;
              if (id) load(id);
            }}
            className="ml-2"
          >
            <option value="">New…</option>
            {portfolios.map((p) => (
              <option key={p.id} value={p.id ?? ""}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="mb-4">
        <label>
          Name
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            style={{ marginLeft: "0.5rem" }}
          />
        </label>
      </div>

      <fieldset className="mb-4">
        <legend>Include Accounts</legend>
        {owners.map((o) => (
          <div key={o.owner} style={{ marginBottom: "0.25rem" }}>
            <strong>{getOwnerDisplayName(ownerLookup, o.owner, o.owner)}</strong>
            {o.accounts.map((a) => {
              const val = `${o.owner}:${a}`;
              return (
                <label key={val} style={{ marginLeft: "0.5rem" }}>
                  <input
                    type="checkbox"
                    checked={accounts.includes(val)}
                    onChange={() => toggleAccount(val)}
                  />
                  {a}
                </label>
              );
            })}
          </div>
        ))}
      </fieldset>

      <div className="mb-4">
        <h3>Synthetic Holdings</h3>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <th>Ticker</th>
              <th>Units</th>
              <th>Price</th>
              <th>Date</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {holdings.map((h, i) => (
              <tr key={i}>
                <td>
                  <input
                    value={h.ticker}
                    onChange={(e) => updateHolding(i, "ticker", e.target.value)}
                  />
                </td>
                <td>
                  <input
                    type="number"
                    value={h.units}
                    onChange={(e) =>
                      updateHolding(i, "units", parseFloat(e.target.value))
                    }
                  />
                </td>
                <td>
                  <input
                    type="number"
                    value={h.price ?? ""}
                    onChange={(e) =>
                      updateHolding(i, "price", parseFloat(e.target.value))
                    }
                  />
                </td>
                <td>
                  <input
                    type="date"
                    value={h.purchase_date ?? ""}
                    onChange={(e) =>
                      updateHolding(i, "purchase_date", e.target.value)
                    }
                  />
                </td>
                <td>
                  <button onClick={() => removeHolding(i)}>✕</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <button onClick={addHolding} style={{ marginTop: "0.5rem" }}>
          Add Holding
        </button>
      </div>

      <div className="mt-4">
        <button onClick={handleSave} className="mr-2">
          Save
        </button>
        {selected != null && (
          <button onClick={handleDelete} className="mr-2">
            Delete
          </button>
        )}
        <a href="/">Back</a>
      </div>
    </div>
  );
}

export default VirtualPortfolio;

