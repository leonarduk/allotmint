import { useCallback, useEffect, useMemo, useState } from "react";
import { getAllowances, getPortfolio, harvestTax } from "../api";
import EmptyState from "../components/EmptyState";
import { useRoute } from "../RouteContext";
import type { Account, Holding } from "../types";

type Position = {
  ticker: string;
  basis: number;
  price: number;
};

type Trade = {
  ticker: string;
  loss: number;
};

type HarvestCandidate = {
  id: string;
  ticker: string;
  name: string;
  account: string;
  units: number;
  basisPerUnit: number;
  price: number;
  costBasis: number;
  marketValue: number;
  loss: number;
  lossPct: number;
};

type AllowanceInfo = {
  used: number;
  limit: number;
  remaining: number;
};

type AllowanceMap = Record<string, AllowanceInfo>;

interface HarvestFormState {
  ticker: string;
  basis: string;
  price: string;
}

function InputField({
  placeholder,
  type = "text",
  value,
  onChange,
}: {
  placeholder: string;
  type?: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <input
      placeholder={placeholder}
      type={type}
      className="rounded border px-2 py-1"
      value={value}
      onChange={(event) => onChange(event.target.value)}
    />
  );
}

function useHarvestForm() {
  const [form, setForm] = useState<HarvestFormState>({
    ticker: "",
    basis: "",
    price: "",
  });

  const updateField = useCallback(
    (field: keyof HarvestFormState) => (value: string) => {
      setForm((prev) => ({ ...prev, [field]: value }));
    },
    [],
  );

  const position = useMemo<Position | null>(() => {
    const basis = parseFloat(form.basis);
    const price = parseFloat(form.price);

    if (!form.ticker || Number.isNaN(basis) || Number.isNaN(price)) {
      return null;
    }

    return {
      ticker: form.ticker,
      basis,
      price,
    };
  }, [form]);

  return {
    form,
    updateField,
    position,
  } as const;
}

function coerceNumber(value: unknown): number | null {
  if (typeof value === "number") {
    return Number.isFinite(value) ? value : null;
  }
  if (typeof value === "string") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function getCandidateFromHolding(
  holding: Holding,
  account: Account,
  owner: string,
  accountIndex: number,
  holdingIndex: number,
): HarvestCandidate | null {
  const units = coerceNumber(holding.units) ?? 0;
  if (!holding.ticker || units <= 0) return null;

  const basisTotal =
    coerceNumber(holding.cost_basis_gbp) ??
    coerceNumber(holding.effective_cost_basis_gbp);
  if (!basisTotal || basisTotal <= 0) return null;

  const basisPerUnit = basisTotal / units;
  if (!Number.isFinite(basisPerUnit)) return null;

  const explicitPrice = coerceNumber(holding.current_price_gbp);
  const marketValue =
    coerceNumber(holding.market_value_gbp) ??
    (explicitPrice !== null ? explicitPrice * units : null);
  if (!marketValue || marketValue <= 0) return null;

  const price = explicitPrice ?? marketValue / units;
  if (!Number.isFinite(price)) return null;

  const loss = basisTotal - marketValue;
  if (!(loss > 0)) return null;

  const lossPct = (loss / basisTotal) * 100;

  return {
    id: `${owner}:${account.account_type}:${holding.ticker}:${accountIndex}:${holdingIndex}`,
    ticker: holding.ticker,
    name: holding.name ?? holding.ticker,
    account: account.account_type,
    units,
    basisPerUnit,
    price,
    costBasis: basisTotal,
    marketValue,
    loss,
    lossPct,
  };
}

function flattenHarvestCandidates(owner: string, accounts: Account[]) {
  const candidates: HarvestCandidate[] = [];
  accounts.forEach((account, accountIndex) => {
    account.holdings.forEach((holding, holdingIndex) => {
      const candidate = getCandidateFromHolding(
        holding,
        account,
        owner,
        accountIndex,
        holdingIndex,
      );
      if (candidate) candidates.push(candidate);
    });
  });

  return candidates.sort((a, b) => b.loss - a.loss);
}

function useHarvestCandidates(owner: string | null | undefined) {
  const [candidates, setCandidates] = useState<HarvestCandidate[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;
    if (!owner) {
      setCandidates([]);
      setError(null);
      setLoading(false);
      return () => {
        isMounted = false;
      };
    }

    setLoading(true);
    getPortfolio(owner)
      .then((portfolio) => {
        if (!isMounted) return;
        setCandidates(flattenHarvestCandidates(owner, portfolio.accounts));
        setError(null);
      })
      .catch((err) => {
        if (!isMounted) return;
        const msg = err instanceof Error ? err.message : String(err);
        setError(msg);
        setCandidates([]);
      })
      .finally(() => {
        if (!isMounted) return;
        setLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, [owner]);

  return { candidates, loading, error } as const;
}

function TaxHarvestSection() {
  const { selectedOwner } = useRoute();
  const { candidates, loading, error: holdingsError } = useHarvestCandidates(
    selectedOwner,
  );
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [threshold, setThreshold] = useState(0);
  const { form, updateField, position } = useHarvestForm();
  const [trades, setTrades] = useState<Trade[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);

  const currencyFormatter = useMemo(
    () =>
      new Intl.NumberFormat(undefined, {
        style: "currency",
        currency: "GBP",
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      }),
    [],
  );

  const percentFormatter = useMemo(
    () =>
      new Intl.NumberFormat(undefined, {
        style: "percent",
        minimumFractionDigits: 1,
        maximumFractionDigits: 1,
      }),
    [],
  );

  useEffect(() => {
    setSelectedIds((prev) => {
      const valid = prev.filter((id) => candidates.some((c) => c.id === id));
      if (valid.length > 0 || candidates.length === 0) {
        return valid;
      }
      return candidates.slice(0, 1).map((candidate) => candidate.id);
    });
  }, [candidates]);

  const selectedPositions = useMemo(() => {
    const map = new Map(candidates.map((candidate) => [candidate.id, candidate]));
    return selectedIds
      .map((id) => map.get(id))
      .filter((candidate): candidate is HarvestCandidate => Boolean(candidate))
      .map((candidate) => ({
        ticker: candidate.ticker,
        basis: candidate.basisPerUnit,
        price: candidate.price,
      }));
  }, [candidates, selectedIds]);

  const handleHarvest = useCallback(async () => {
    const payload: Position[] = [...selectedPositions];

    if (position) {
      payload.push(position);
    }

    if (payload.length === 0) {
      setError("Select at least one position or add a manual entry");
      return;
    }

    setIsLoading(true);
    try {
      const response = await harvestTax(payload, threshold);
      setTrades(response.trades);
      setError(null);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg);
      setTrades(null);
    } finally {
      setIsLoading(false);
    }
  }, [position, selectedPositions, threshold]);

  const thresholdLabel = useMemo(() => `${threshold}%`, [threshold]);

  return (
    <section aria-labelledby="tax-harvest-heading" className="flex flex-col gap-4">
      <div>
        <h2 id="tax-harvest-heading" className="text-xl md:text-2xl">
          Tax Harvest
        </h2>
        <p className="text-sm text-gray-500">
          Model potential loss harvesting opportunities from your positions.
        </p>
      </div>

      {!selectedOwner && (
        <p className="text-sm text-gray-500">
          Select an owner to view harvest candidates.
        </p>
      )}

      {selectedOwner && (
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <h3 className="text-lg font-semibold">
              Top loss candidates for {selectedOwner}
            </h3>
            {loading && <div>Loading holdings…</div>}
            {holdingsError && (
              <p className="text-red-500">Failed to load holdings: {holdingsError}</p>
            )}
            {!loading && !holdingsError && candidates.length === 0 && (
              <p>No qualifying loss positions were found.</p>
            )}
            {!loading && !holdingsError && candidates.length > 0 && (
              <div className="overflow-x-auto">
                <table
                  className="min-w-full border-collapse border border-gray-200 text-sm"
                  data-testid="harvest-candidates"
                >
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="border px-2 py-1 text-left">Select</th>
                      <th className="border px-2 py-1 text-left">Ticker</th>
                      <th className="border px-2 py-1 text-left">Name</th>
                      <th className="border px-2 py-1 text-left">Account</th>
                      <th className="border px-2 py-1 text-right">Units</th>
                      <th className="border px-2 py-1 text-right">Cost</th>
                      <th className="border px-2 py-1 text-right">Market value</th>
                      <th className="border px-2 py-1 text-right">Loss (£)</th>
                      <th className="border px-2 py-1 text-right">Loss (%)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {candidates.map((candidate) => {
                      const isSelected = selectedIds.includes(candidate.id);
                      return (
                        <tr key={candidate.id} className={isSelected ? "bg-blue-50" : undefined}>
                          <td className="border px-2 py-1 text-center">
                            <input
                              type="checkbox"
                              aria-label={`Select ${candidate.ticker}`}
                              checked={isSelected}
                              onChange={(event) => {
                                setSelectedIds((prev) => {
                                  if (event.target.checked) {
                                    if (prev.includes(candidate.id)) {
                                      return prev;
                                    }
                                    return [...prev, candidate.id];
                                  }
                                  return prev.filter((id) => id !== candidate.id);
                                });
                              }}
                            />
                          </td>
                          <td className="border px-2 py-1 font-mono">{candidate.ticker}</td>
                          <td className="border px-2 py-1">{candidate.name}</td>
                          <td className="border px-2 py-1 capitalize">{candidate.account}</td>
                          <td className="border px-2 py-1 text-right">
                            {candidate.units.toLocaleString(undefined, {
                              maximumFractionDigits: 2,
                            })}
                          </td>
                          <td className="border px-2 py-1 text-right">
                            {currencyFormatter.format(candidate.costBasis)}
                          </td>
                          <td className="border px-2 py-1 text-right">
                            {currencyFormatter.format(candidate.marketValue)}
                          </td>
                          <td className="border px-2 py-1 text-right">
                            {currencyFormatter.format(-candidate.loss)}
                          </td>
                          <td className="border px-2 py-1 text-right">
                            {percentFormatter.format(-candidate.lossPct / 100)}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <div className="flex flex-col gap-2">
            <label htmlFor="harvest-threshold" className="text-sm font-medium">
              Loss threshold ({thresholdLabel})
            </label>
            <input
              id="harvest-threshold"
              type="range"
              min="0"
              max="50"
              step="1"
              value={threshold}
              onChange={(event) => setThreshold(Number(event.target.value))}
            />
            <p className="text-xs text-gray-500">
              Only trades with losses greater than this percentage of basis will be
              suggested.
            </p>
          </div>

          <div className="flex flex-col gap-2">
            <button
              type="button"
              className="w-fit rounded border px-3 py-1 text-sm"
              onClick={() => setShowAdvanced((prev) => !prev)}
            >
              {showAdvanced ? "Hide advanced" : "Advanced"}
            </button>
            {showAdvanced && (
              <div className="flex flex-col gap-2 max-w-sm" data-testid="advanced-form">
                <InputField
                  placeholder="Ticker"
                  value={form.ticker}
                  onChange={updateField("ticker")}
                />
                <InputField
                  placeholder="Basis per unit"
                  type="number"
                  value={form.basis}
                  onChange={updateField("basis")}
                />
                <InputField
                  placeholder="Price"
                  type="number"
                  value={form.price}
                  onChange={updateField("price")}
                />
              </div>
            )}
          </div>

          <button
            type="button"
            className="w-fit rounded border px-4 py-2"
            onClick={handleHarvest}
            disabled={isLoading}
          >
            Run Harvest
          </button>
        </div>
      )}

      {isLoading && <div data-testid="spinner">Loading...</div>}
      {error && <p className="text-red-500">{error}</p>}
      {trades && trades.length > 0 && (
        <div className="flex flex-col gap-2" data-testid="harvest-results">
          <p className="font-medium">
            Total realized loss: {currencyFormatter.format(
              trades.reduce((sum, trade) => sum + (trade.loss ?? 0), 0) * -1,
            )}
          </p>
          <ul className="list-disc pl-5 text-sm">
            {trades.map(({ ticker, loss }, index) => (
              <li key={`${ticker}-${index}`}>
                {ticker}: {currencyFormatter.format(-loss)}
              </li>
            ))}
          </ul>
        </div>
      )}
      {trades && trades.length === 0 && <p>No trades qualify</p>}
    </section>
  );
}

function formatAllowanceValue(value: number) {
  return value.toFixed(2);
}

function TaxAllowancesSection() {
  const [data, setData] = useState<AllowanceMap | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let isMounted = true;
    getAllowances()
      .then((response) => {
        if (!isMounted) return;
        setData(response.allowances);
        setError(null);
      })
      .catch(() => {
        if (!isMounted) return;
        setError("Failed to load allowances");
      })
      .finally(() => {
        if (!isMounted) return;
        setLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, []);

  if (loading) return <p>Loading...</p>;
  if (error) return <p className="text-red-500">{error}</p>;
  if (!data) return <EmptyState message="No data" />;

  return (
    <section aria-labelledby="tax-allowances-heading" className="flex flex-col gap-4">
      <div>
        <h2 id="tax-allowances-heading" className="text-xl md:text-2xl">
          Tax Allowances
        </h2>
        <p className="text-sm text-gray-500">
          Track how much of each allowance you have used and what remains.
        </p>
      </div>
      <table className="min-w-full border-collapse border border-gray-300">
        <thead>
          <tr>
            <th className="border p-2 text-left">Account</th>
            <th className="border p-2 text-right">Used</th>
            <th className="border p-2 text-right">Available</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(data).map(([type, info]) => (
            <tr key={type}>
              <td className="border p-2 capitalize">{type}</td>
              <td className="border p-2 text-right">{formatAllowanceValue(info.used)}</td>
              <td className="border p-2 text-right">{formatAllowanceValue(info.remaining)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

export default function TaxTools() {
  return (
    <div className="flex flex-col gap-8">
      <header>
        <h1 className="mb-2 text-2xl md:text-4xl">Tax Tools</h1>
        <p className="text-gray-600">
          Run quick harvest scenarios and keep tabs on your annual allowances in
          one place.
        </p>
      </header>
      <TaxHarvestSection />
      <TaxAllowancesSection />
    </div>
  );
}
