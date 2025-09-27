import { useCallback, useEffect, useMemo, useState } from "react";
import { getAllowances, harvestTax } from "../api";
import EmptyState from "../components/EmptyState";
import { useRoute } from "../RouteContext";

type Position = {
  ticker: string;
  basis: number;
  price: number;
};

type Trade = {
  ticker: string;
  loss: number;
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

interface HarvestFormState {
  ticker: string;
  basis: string;
  price: string;
  threshold: string;
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
    threshold: "",
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

  const threshold = useMemo(() => {
    const parsed = parseFloat(form.threshold);
    return Number.isNaN(parsed) ? null : parsed;
  }, [form.threshold]);

  return {
    form,
    updateField,
    position,
    threshold,
  } as const;
}

function TaxHarvestSection() {
  const { form, updateField, position, threshold } = useHarvestForm();
  const [trades, setTrades] = useState<Trade[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const handleHarvest = useCallback(async () => {
    if (!position || threshold === null) {
      setError("Please fill out all fields with valid values");
      return;
    }

    setIsLoading(true);
    try {
      const response = await harvestTax([position], threshold);
      setTrades(response.trades);
      setError(null);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg);
      setTrades(null);
    } finally {
      setIsLoading(false);
    }
  }, [position, threshold]);

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
      <div className="flex flex-col gap-2 max-w-sm">
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
        <InputField
          placeholder="Threshold"
          type="number"
          value={form.threshold}
          onChange={updateField("threshold")}
        />
      </div>
      <button
        type="button"
        className="w-fit rounded border px-4 py-2"
        onClick={handleHarvest}
        disabled={isLoading}
      >
        Run Harvest
      </button>
      {isLoading && <div data-testid="spinner">Loading...</div>}
      {error && <p className="text-red-500">{error}</p>}
      {trades && trades.length > 0 && (
        <ul data-testid="harvest-results" className="list-disc pl-5">
          {trades.map(({ ticker, loss }, index) => (
            <li key={`${ticker}-${index}`}>
              {ticker}: {loss}
            </li>
          ))}
        </ul>
      )}
      {trades && trades.length === 0 && <p>No trades qualify</p>}
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
