import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ChangeEvent,
} from "react";
import { getAllowances, getOwners, getPortfolio, harvestTax } from "../api";
import EmptyState from "../components/EmptyState";
import { useRoute } from "../RouteContext";
import type { Holding, OwnerSummary, Portfolio } from "../types";
import { sanitizeOwners } from "../utils/owners";

type Trade = {
  ticker: string;
  loss: number;
};

type Position = {
  ticker: string;
  basis: number;
  price: number;
};

type HarvestCandidate = {
  id: string;
  ticker: string;
  name: string;
  account: string;
  units: number;
  basisPerUnit: number;
  latestPrice: number;
  costBasis: number;
  marketValue: number;
  lossValue: number;
  lossPct: number;
};

type AllowanceInfo = {
  used: number;
  limit: number;
  remaining: number;
};

type AllowanceMap = Record<string, AllowanceInfo>;

type AllowanceResponse = {
  owner: string;
  tax_year: string;
  allowances: AllowanceMap;
};

function useOwnersList() {
  const [owners, setOwners] = useState<OwnerSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;
    setLoading(true);
    setError(null);
    getOwners()
      .then((response) => {
        if (!isMounted) return;
        setOwners(sanitizeOwners(response));
      })
      .catch(() => {
        if (!isMounted) return;
        setOwners([]);
        setError("Failed to load owners");
      })
      .finally(() => {
        if (!isMounted) return;
        setLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, []);

  return { owners, loading, error } as const;
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
  const [form, setForm] = useState({
    ticker: "",
    basis: "",
    price: "",
  });

  const updateField = useCallback(
    (field: keyof typeof form) => (value: string) => {
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

function formatPercent(value: number) {
  return `${value.toFixed(2)}%`;
}

function buildCandidateId(account: string, holding: Holding, index: number) {
  return `${account}-${holding.ticker}-${holding.acquired_date ?? index}`;
}

function useHarvestCandidates(owner?: string) {
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;
    if (!owner) {
      setPortfolio(null);
      setLoading(false);
      setError(null);
      return () => {
        isMounted = false;
      };
    }

    setLoading(true);
    setError(null);
    getPortfolio(owner)
      .then((data) => {
        if (!isMounted) return;
        setPortfolio(data);
      })
      .catch(() => {
        if (!isMounted) return;
        setError("Failed to load portfolio");
        setPortfolio(null);
      })
      .finally(() => {
        if (!isMounted) return;
        setLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, [owner]);

  const candidates = useMemo<HarvestCandidate[]>(() => {
    if (!portfolio) return [];

    const flattened: HarvestCandidate[] = [];

    portfolio.accounts.forEach((account) => {
      account.holdings.forEach((holding, index) => {
        if (!holding.units || holding.units <= 0) {
          return;
        }

        const totalCost =
          holding.cost_basis_gbp ?? holding.effective_cost_basis_gbp ?? null;
        if (totalCost == null) {
          return;
        }

        const marketValue =
          holding.market_value_gbp ??
          (holding.current_price_gbp != null
            ? holding.current_price_gbp * holding.units
            : null);
        if (marketValue == null) {
          return;
        }

        const gain = holding.gain_gbp ?? marketValue - totalCost;
        if (gain >= 0) {
          return;
        }

        const basisPerUnit = totalCost / holding.units;
        const latestPrice =
          holding.current_price_gbp ?? marketValue / holding.units;
        const lossValue = Math.abs(gain);
        const lossPct = totalCost !== 0 ? (lossValue / totalCost) * 100 : 0;

        flattened.push({
          id: buildCandidateId(account.account_type, holding, index),
          ticker: holding.ticker,
          name: holding.name,
          account: account.account_type,
          units: holding.units,
          basisPerUnit,
          latestPrice,
          costBasis: totalCost,
          marketValue,
          lossValue,
          lossPct,
        });
      });
    });

    return flattened.sort((a, b) => b.lossValue - a.lossValue);
  }, [portfolio]);

  return { candidates, loading, error } as const;
}

function TaxHarvestSection() {
  const { selectedOwner } = useRoute();
  const { form, updateField, position: manualPosition } = useHarvestForm();
  const { candidates, loading: candidatesLoading, error: candidateError } =
    useHarvestCandidates(selectedOwner);
  const [trades, setTrades] = useState<Trade[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [threshold, setThreshold] = useState(0);
  const [advanced, setAdvanced] = useState(false);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);

  useEffect(() => {
    setSelectedIds([]);
    setTrades(null);
    setError(null);
  }, [selectedOwner]);

  const selectedCandidates = useMemo(
    () =>
      candidates.filter((candidate) => selectedIds.includes(candidate.id)),
    [candidates, selectedIds],
  );

  const manualPositionPayload = useMemo(() => {
    if (!advanced) return null;
    return manualPosition;
  }, [advanced, manualPosition]);

  const handleHarvest = useCallback(async () => {
    const manualPositions: Position[] = manualPositionPayload
      ? [manualPositionPayload]
      : [];
    const candidatePositions = selectedCandidates.map((candidate) => ({
      ticker: candidate.ticker,
      basis: candidate.basisPerUnit,
      price: candidate.latestPrice,
    }));

    const positions = [...candidatePositions, ...manualPositions];

    if (positions.length === 0) {
      setError("Select a position or enter one manually to model a harvest");
      return;
    }

    setIsLoading(true);
    try {
      const response = await harvestTax(positions, threshold);
      setTrades(response.trades);
      setError(null);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg);
      setTrades(null);
    } finally {
      setIsLoading(false);
    }
  }, [manualPositionPayload, selectedCandidates, threshold]);

  useEffect(() => {
    if (!candidateError) return;
    setError(candidateError);
  }, [candidateError]);

  const totalLoss = useMemo(
    () =>
      trades?.reduce(
        (acc, trade) => acc + (typeof trade.loss === "number" ? trade.loss : 0),
        0,
      ) ?? 0,
    [trades],
  );

  const toggleSelection = useCallback((id: string) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((current) => current !== id) : [...prev, id],
    );
  }, []);

  const anySelection = selectedCandidates.length > 0 || !!manualPositionPayload;

  useEffect(() => {
    if (
      error &&
      error.toLowerCase().includes("select a position") &&
      anySelection
    ) {
      setError(null);
    }
  }, [anySelection, error]);

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
        <EmptyState message="Choose a portfolio owner to see harvest candidates." />
      )}
      {selectedOwner && (
        <>
          <div className="flex flex-col gap-3">
            <label className="flex flex-col gap-2">
              <span className="text-sm font-medium text-gray-700">
                Minimum loss threshold: {threshold}%
              </span>
              <input
                type="range"
                min={0}
                max={100}
                step={1}
                value={threshold}
                onChange={(event) => setThreshold(Number(event.target.value))}
              />
            </label>
          </div>
          {candidatesLoading ? (
            <div data-testid="candidate-loading">Loading candidates...</div>
          ) : candidates.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="min-w-full border-collapse border border-gray-300 text-sm">
                <thead className="bg-gray-100">
                  <tr>
                    <th className="border p-2 text-left">Holding</th>
                    <th className="border p-2 text-right">Units</th>
                    <th className="border p-2 text-right">Basis / unit</th>
                    <th className="border p-2 text-right">Price</th>
                    <th className="border p-2 text-right">Cost basis</th>
                    <th className="border p-2 text-right">Market value</th>
                    <th className="border p-2 text-right">Loss</th>
                  </tr>
                </thead>
                <tbody>
                  {candidates.map((candidate) => {
                    const isChecked = selectedIds.includes(candidate.id);
                    return (
                      <tr key={candidate.id} className={isChecked ? "bg-amber-50" : undefined}>
                        <td className="border p-2 align-top">
                          <label className="flex flex-col gap-1">
                            <span className="flex items-center gap-2">
                              <input
                                type="checkbox"
                                checked={isChecked}
                                onChange={() => toggleSelection(candidate.id)}
                              />
                              <span className="font-medium">{candidate.ticker}</span>
                            </span>
                            <span className="text-xs text-gray-500">
                              {candidate.name} · {candidate.account.toUpperCase()}
                            </span>
                          </label>
                        </td>
                        <td className="border p-2 text-right">{candidate.units.toLocaleString()}</td>
                        <td className="border p-2 text-right">{currencyFormatter.format(candidate.basisPerUnit)}</td>
                        <td className="border p-2 text-right">{currencyFormatter.format(candidate.latestPrice)}</td>
                        <td className="border p-2 text-right">{currencyFormatter.format(candidate.costBasis)}</td>
                        <td className="border p-2 text-right">{currencyFormatter.format(candidate.marketValue)}</td>
                        <td className="border p-2 text-right text-red-600">
                          -{currencyFormatter.format(candidate.lossValue)}
                          <div className="text-xs">-{formatPercent(candidate.lossPct)}</div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState message="No clear loss candidates found." />
          )}
          <div className="flex items-center gap-2">
            <input
              id="harvest-advanced-toggle"
              type="checkbox"
              checked={advanced}
              onChange={(event) => setAdvanced(event.target.checked)}
            />
            <label htmlFor="harvest-advanced-toggle" className="text-sm">
              Advanced: add manual position
            </label>
          </div>
          {advanced && (
            <div className="grid max-w-xl grid-cols-1 gap-2 sm:grid-cols-2">
              <InputField
                placeholder="Ticker"
                value={form.ticker}
                onChange={updateField("ticker")}
              />
              <InputField
                placeholder="Basis"
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
        </>
      )}
      <button
        type="button"
        className="w-fit rounded border px-4 py-2"
        onClick={handleHarvest}
        disabled={isLoading || !selectedOwner}
      >
        Run Harvest
      </button>
      {isLoading && <div data-testid="spinner">Loading...</div>}
      {error && <p className="text-red-500">{error}</p>}
      {trades && trades.length > 0 && (
        <div className="rounded-md border border-gray-200 bg-gray-50 p-4 text-sm" data-testid="harvest-results">
          <p className="font-medium">Modeled trades</p>
          <ul className="mt-2 list-disc pl-5">
            {trades.map(({ ticker, loss }, index) => (
              <li key={`${ticker}-${index}`}>
                {ticker}: {currencyFormatter.format(loss)} loss
              </li>
            ))}
          </ul>
          <p className="mt-3 text-gray-700">
            Total modeled loss: {currencyFormatter.format(totalLoss)}
          </p>
        </div>
      )}
      {trades && trades.length === 0 && <p>No trades qualify</p>}
      {!anySelection && selectedOwner && !isLoading && !candidateError && (
        <p className="text-sm text-gray-500">
          Tip: select one or more candidates above or use the advanced form.
        </p>
      )}
    </section>
  );
}

const currencyFormatter = new Intl.NumberFormat(undefined, {
  style: "currency",
  currency: "GBP",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

function formatAllowanceValue(value: number) {
  return currencyFormatter.format(value);
}

function TaxAllowancesSection() {
  const { selectedOwner } = useRoute();
  const [data, setData] = useState<AllowanceResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let isMounted = true;
    if (!selectedOwner) {
      setData(null);
      setError(null);
      setLoading(false);
      return () => {
        isMounted = false;
      };
    }

    setLoading(true);
    getAllowances(selectedOwner)
      .then((response) => {
        if (!isMounted) return;
        setData(response);
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
  }, [selectedOwner]);

  if (!selectedOwner) {
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
        <EmptyState message="Choose a portfolio owner to see their allowance usage." />
      </section>
    );
  }

  if (loading) return <p>Loading...</p>;
  if (error) return <p className="text-red-500">{error}</p>;
  if (!data) return <EmptyState message="No data" />;

  const entries = Object.entries(data.allowances);
  const totals = entries.reduce(
    (acc, [, info]) => {
      return {
        used: acc.used + info.used,
        limit: acc.limit + info.limit,
        remaining: acc.remaining + Math.max(info.remaining, 0),
      };
    },
    { used: 0, limit: 0, remaining: 0 },
  );

  const outstandingAllowances = entries
    .filter(([, info]) => info.remaining > 0)
    .map(([type, info]) => `${type.toUpperCase()} (${formatAllowanceValue(info.remaining)})`)
    .join(", ");

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
      <div className="rounded-md border border-gray-200 bg-gray-50 p-4 text-sm text-gray-700">
        <div className="flex flex-wrap gap-3">
          <span>Tax year {data.tax_year}</span>
          <span>
            Used {formatAllowanceValue(totals.used)} of {formatAllowanceValue(totals.limit)} total
          </span>
          <span>
            {totals.remaining > 0
              ? `Outstanding: ${outstandingAllowances || formatAllowanceValue(totals.remaining)}`
              : "All allowances fully used"}
          </span>
        </div>
      </div>
      <table className="min-w-full border-collapse border border-gray-300">
        <thead>
          <tr>
            <th className="border p-2 text-left">Account</th>
            <th className="border p-2 text-right">Limit</th>
            <th className="border p-2 text-right">Used</th>
            <th className="border p-2 text-right">Available</th>
            <th className="border p-2 text-right">Usage</th>
          </tr>
        </thead>
        <tbody>
          {entries.map(([type, info]) => {
            const percentUsed = info.limit > 0 ? (info.used / info.limit) * 100 : info.used > 0 ? 100 : 0;
            const clampedPercent = Math.min(Math.max(percentUsed, 0), 100);
            const roundedPercent = Math.round(percentUsed);
            let progressColor = "bg-emerald-500";
            let textColor = "text-emerald-600";
            if (percentUsed >= 100) {
              progressColor = "bg-red-500";
              textColor = "text-red-600";
            } else if (percentUsed >= 90) {
              progressColor = "bg-amber-500";
              textColor = "text-amber-600";
            }

            return (
              <tr key={type}>
                <td className="border p-2 capitalize">{type}</td>
                <td className="border p-2 text-right">{formatAllowanceValue(info.limit)}</td>
                <td className="border p-2 text-right">{formatAllowanceValue(info.used)}</td>
                <td className="border p-2 text-right">{formatAllowanceValue(info.remaining)}</td>
                <td className="border p-2 text-right">
                  <div className="flex items-center justify-end gap-2">
                    <div className="h-2 w-24 rounded-full bg-gray-200" aria-hidden="true">
                      <div
                        className={`h-2 rounded-full ${progressColor}`}
                        style={{ width: `${clampedPercent}%` }}
                      />
                    </div>
                    <span className={`text-xs font-medium ${textColor}`}>{roundedPercent}%</span>
                  </div>
                  <span className="sr-only">
                    Used {formatAllowanceValue(info.used)} of {formatAllowanceValue(info.limit)} ({roundedPercent}%)
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}

export default function TaxTools() {
  const { selectedOwner, setSelectedOwner } = useRoute();
  const {
    owners,
    loading: ownersLoading,
    error: ownersError,
  } = useOwnersList();

  useEffect(() => {
    if (!selectedOwner) return;
    if (!owners.length) return;
    const isValid = owners.some((owner) => owner.owner === selectedOwner);
    if (!isValid) {
      setSelectedOwner("");
    }
  }, [owners, selectedOwner, setSelectedOwner]);

  const ownerSelectValue = useMemo(() => {
    if (!selectedOwner) return "";
    return owners.some((owner) => owner.owner === selectedOwner)
      ? selectedOwner
      : "";
  }, [owners, selectedOwner]);

  const handleOwnerChange = useCallback(
    (event: ChangeEvent<HTMLSelectElement>) => {
      setSelectedOwner(event.target.value);
    },
    [setSelectedOwner],
  );

  const ownerSelectDisabled =
    ownersLoading || ownersError !== null || owners.length === 0;

  return (
    <div className="flex flex-col gap-8">
      <header className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="mb-2 text-2xl md:text-4xl">Tax Tools</h1>
          <p className="text-gray-600">
            Run quick harvest scenarios and keep tabs on your annual allowances in
            one place.
          </p>
        </div>
        <div className="md:w-64">
          <label
            htmlFor="tax-owner-select"
            className="flex flex-col gap-1 text-sm font-medium text-gray-700"
          >
            Portfolio owner
            <select
              id="tax-owner-select"
              className="rounded border border-gray-300 px-3 py-2 text-base"
              value={ownerSelectValue}
              onChange={handleOwnerChange}
              disabled={ownerSelectDisabled}
            >
              <option value="">Select an owner</option>
              {owners.map((owner) => (
                <option key={owner.owner} value={owner.owner}>
                  {owner.owner}
                </option>
              ))}
            </select>
          </label>
          {ownersLoading && (
            <p className="mt-1 text-xs text-gray-500">Loading owners...</p>
          )}
          {!ownersLoading && ownersError && (
            <p className="mt-1 text-xs text-red-500">{ownersError}</p>
          )}
          {!ownersLoading && !ownersError && owners.length === 0 && (
            <p className="mt-1 text-xs text-gray-500">No owners available.</p>
          )}
        </div>
      </header>
      <TaxHarvestSection />
      <TaxAllowancesSection />
    </div>
  );
}
