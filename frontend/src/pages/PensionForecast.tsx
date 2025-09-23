import { useEffect, useMemo, useState, type ReactNode } from "react";
import {
  LineChart,
  Line,
  ResponsiveContainer,
  XAxis,
  YAxis,
  Tooltip,
} from "recharts";
import {
  getOwners,
  getPensionForecast,
  type PensionIncomeBreakdown,
} from "../api";
import type { OwnerSummary } from "../types";
import { OwnerSelector } from "../components/OwnerSelector";
import { useTranslation } from "react-i18next";

export default function PensionForecast() {
  const [owners, setOwners] = useState<OwnerSummary[]>([]);
  const [owner, setOwner] = useState("");
  const [deathAge, setDeathAge] = useState(90);
  const [statePension, setStatePension] = useState<string>("");
  const [monthlySpending, setMonthlySpending] = useState(2500);
  const [monthlySavings, setMonthlySavings] = useState(400);
  const [data, setData] = useState<{ age: number; income: number }[]>([]);
  const [projectedPot, setProjectedPot] = useState<number | null>(null);
  const [pensionPot, setPensionPot] = useState<number | null>(null);
  const [currentAge, setCurrentAge] = useState<number | null>(null);
  const [retirementAge, setRetirementAge] = useState<number | null>(null);
  const [dob, setDob] = useState<string | null>(null);
  const [earliestRetirementAge, setEarliestRetirementAge] =
    useState<number | null>(null);
  const [retirementIncomeBreakdown, setRetirementIncomeBreakdown] =
    useState<PensionIncomeBreakdown | null>(null);
  const [retirementIncomeTotal, setRetirementIncomeTotal] = useState<
    number | null
  >(null);
  const [desiredIncomeUsed, setDesiredIncomeUsed] = useState<number | null>(
    null,
  );
  const [err, setErr] = useState<string | null>(null);
  const { t } = useTranslation();

  const careerPathOptions = useMemo(
    () => [
      {
        id: "steady",
        label: t("pensionForecast.careerPath.options.steady.label"),
        description: t("pensionForecast.careerPath.options.steady.description"),
        growth: 3,
      },
      {
        id: "balanced",
        label: t("pensionForecast.careerPath.options.balanced.label"),
        description: t("pensionForecast.careerPath.options.balanced.description"),
        growth: 5,
      },
      {
        id: "accelerated",
        label: t("pensionForecast.careerPath.options.accelerated.label"),
        description: t("pensionForecast.careerPath.options.accelerated.description"),
        growth: 7,
      },
    ],
    [t],
  );

  const [careerPathIndex, setCareerPathIndex] = useState(() => {
    const defaultIdx = careerPathOptions.findIndex((option) => option.growth === 5);
    return defaultIdx >= 0 ? defaultIdx : 0;
  });

  useEffect(() => {
    if (careerPathIndex >= careerPathOptions.length) {
      setCareerPathIndex(Math.max(0, careerPathOptions.length - 1));
    }
  }, [careerPathIndex, careerPathOptions.length]);

  const selectedCareerPath =
    careerPathOptions[careerPathIndex] ??
    careerPathOptions[careerPathOptions.length - 1] ??
    careerPathOptions[0];
  const investmentGrowthPct = selectedCareerPath?.growth ?? 5;

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
        minimumFractionDigits: 0,
        maximumFractionDigits: 1,
      }),
    [],
  );

  useEffect(() => {
    getOwners()
      .then((os) => {
        setOwners(os);
        if (os.length > 0) {
          setOwner(os[0].owner);
        }
      })
      .catch(() => setOwners([]));
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const contributionMonthlyVal =
        Number.isFinite(monthlySavings) && monthlySavings > 0
          ? monthlySavings
          : undefined;
      const desiredIncomeAnnualVal =
        Number.isFinite(monthlySpending) && monthlySpending > 0
          ? monthlySpending * 12
          : undefined;
      const res = await getPensionForecast({
        owner,
        deathAge,
        statePensionAnnual: statePension
          ? parseFloat(statePension)
          : undefined,
        contributionMonthly: contributionMonthlyVal,
        desiredIncomeAnnual: desiredIncomeAnnualVal,
        investmentGrowthPct,
      });
      setData(res.forecast);
      setProjectedPot(res.projected_pot_gbp + res.pension_pot_gbp);
      setPensionPot(res.pension_pot_gbp);
      setCurrentAge(res.current_age);
      setRetirementAge(res.retirement_age);
      setDob(res.dob || null);
      setEarliestRetirementAge(res.earliest_retirement_age);
      setRetirementIncomeBreakdown(res.retirement_income_breakdown ?? null);
      setRetirementIncomeTotal(res.retirement_income_total_annual ?? null);
      setDesiredIncomeUsed(
        res.desired_income_annual !== undefined
          ? res.desired_income_annual
          : null,
      );
      setErr(null);
    } catch (ex: any) {
      setErr(String(ex));
      setData([]);
      setEarliestRetirementAge(null);
      setRetirementIncomeBreakdown(null);
      setRetirementIncomeTotal(null);
      setDesiredIncomeUsed(null);
    }
  };

  const breakdownConfig: Array<{
    key: keyof PensionIncomeBreakdown;
    label: string;
  }> = [
    {
      key: "state_pension_annual",
      label: t("pensionForecast.incomeSources.state"),
    },
    {
      key: "defined_benefit_annual",
      label: t("pensionForecast.incomeSources.definedBenefit"),
    },
    {
      key: "defined_contribution_annual",
      label: t("pensionForecast.incomeSources.definedContribution"),
    },
  ];

  const breakdownEntries = retirementIncomeBreakdown
    ? breakdownConfig.map(({ key, label }) => {
        const annual = Number(retirementIncomeBreakdown[key] ?? 0);
        const monthly = annual / 12;
        const share =
          retirementIncomeTotal && retirementIncomeTotal > 0
            ? percentFormatter.format(annual / retirementIncomeTotal)
            : "—";
        return { key, label, annual, monthly, share };
      })
    : [];

  const totalAnnualIncomeFormatted =
    retirementIncomeTotal != null
      ? currencyFormatter.format(retirementIncomeTotal)
      : null;
  const totalMonthlyIncomeFormatted =
    retirementIncomeTotal != null
      ? currencyFormatter.format(retirementIncomeTotal / 12)
      : null;

  const monthlySpendingFormatted = currencyFormatter.format(monthlySpending);
  const monthlySavingsFormatted = currencyFormatter.format(monthlySavings);
  const pensionPotDisplay =
    pensionPot != null ? currencyFormatter.format(pensionPot) : null;
  const projectedPotDisplay =
    projectedPot != null ? currencyFormatter.format(projectedPot) : null;
  const projectedPotLabel =
    projectedPot != null && retirementAge != null
      ? t("pensionForecast.projectedPotAt", { age: retirementAge })
      : null;

  let banner:
    | { variant: "success" | "warning" | "info"; message: string }
    | null = null;
  if (desiredIncomeUsed != null && retirementIncomeTotal != null) {
    if (retirementIncomeTotal >= desiredIncomeUsed) {
      banner = {
        variant: "success",
        message:
          earliestRetirementAge != null
            ? t("pensionForecast.prediction.onTrackWithAge", {
                total: currencyFormatter.format(retirementIncomeTotal),
                desired: currencyFormatter.format(desiredIncomeUsed),
                age: earliestRetirementAge,
              })
            : t("pensionForecast.prediction.onTrack", {
                total: currencyFormatter.format(retirementIncomeTotal),
                desired: currencyFormatter.format(desiredIncomeUsed),
              }),
      };
    } else {
      const shortfallAnnual = desiredIncomeUsed - retirementIncomeTotal;
      banner = {
        variant: "warning",
        message:
          earliestRetirementAge != null
            ? t("pensionForecast.prediction.shortfallWithAge", {
                desired: currencyFormatter.format(desiredIncomeUsed),
                shortfallAnnual: currencyFormatter.format(shortfallAnnual),
                shortfallMonthly: currencyFormatter.format(shortfallAnnual / 12),
                age: earliestRetirementAge,
              })
            : t("pensionForecast.prediction.shortfall", {
                desired: currencyFormatter.format(desiredIncomeUsed),
                shortfallAnnual: currencyFormatter.format(shortfallAnnual),
                shortfallMonthly: currencyFormatter.format(shortfallAnnual / 12),
              }),
      };
    }
  } else if (earliestRetirementAge != null) {
    banner = {
      variant: "info",
      message: t("pensionForecast.prediction.earliest", {
        age: earliestRetirementAge,
      }),
    };
  }

  const bannerClassName = banner
    ? {
        success: "border-green-300 bg-green-50 text-green-900",
        warning: "border-yellow-300 bg-yellow-50 text-yellow-900",
        info: "border-blue-300 bg-blue-50 text-blue-900",
      }[banner.variant]
    : "";

  return (
    <div className="space-y-6">
      <h1 className="text-2xl md:text-4xl">Pension Forecast</h1>
      <form onSubmit={handleSubmit} className="space-y-6">
        <div className="grid gap-6 lg:grid-cols-2">
          <Panel
            title={t("pensionForecast.now.title")}
            description={t("pensionForecast.now.description")}
          >
            <OwnerSelector owners={owners} selected={owner} onSelect={setOwner} />
            <SliderControl
              id="monthly-spending"
              label={t("pensionForecast.monthlySpending.label")}
              helperText={t("pensionForecast.monthlySpending.helper")}
              min={0}
              max={10000}
              step={50}
              value={monthlySpending}
              valueFormatter={() => monthlySpendingFormatted}
              onChange={(value) => setMonthlySpending(Math.max(0, Math.round(value)))}
            />
            <SliderControl
              id="monthly-savings"
              label={t("pensionForecast.monthlySavings.label")}
              helperText={t("pensionForecast.monthlySavings.helper")}
              min={0}
              max={5000}
              step={50}
              value={monthlySavings}
              valueFormatter={() => monthlySavingsFormatted}
              onChange={(value) => setMonthlySavings(Math.max(0, Math.round(value)))}
            />
          </Panel>
          <Panel
            title={t("pensionForecast.future.title")}
            description={t("pensionForecast.future.description")}
          >
            <SliderControl
              id="career-path"
              label={t("pensionForecast.careerPath.label")}
              helperText={t("pensionForecast.careerPath.helper", {
                description: selectedCareerPath?.description ?? "",
              })}
              min={0}
              max={careerPathOptions.length - 1}
              step={1}
              value={careerPathIndex}
              valueFormatter={() =>
                `${selectedCareerPath?.label ?? ""} · ${selectedCareerPath?.growth ?? 0}%`
              }
              ariaValueText={selectedCareerPath?.label ?? undefined}
              onChange={(value) => {
                const next = Math.round(value);
                setCareerPathIndex(
                  Math.min(careerPathOptions.length - 1, Math.max(0, next)),
                );
              }}
            />
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label
                  htmlFor="death-age"
                  className="block text-sm font-medium text-slate-700"
                >
                  {t("pensionForecast.deathAgeLabel")}
                </label>
                <input
                  id="death-age"
                  type="number"
                  min={0}
                  className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200"
                  value={deathAge}
                  onChange={(e) => setDeathAge(Number(e.target.value))}
                  required
                />
              </div>
              <div>
                <label
                  htmlFor="state-pension"
                  className="block text-sm font-medium text-slate-700"
                >
                  {t("pensionForecast.statePensionLabel")}
                </label>
                <input
                  id="state-pension"
                  type="number"
                  min={0}
                  className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200"
                  value={statePension}
                  onChange={(e) => setStatePension(e.target.value)}
                />
              </div>
            </div>
            <div className="flex justify-end">
              <button
                type="submit"
                className="rounded-md bg-blue-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-300 focus:ring-offset-1"
              >
                {t("pensionForecast.forecastCta")}
              </button>
            </div>
            <div className="space-y-4">
              {err && <p className="text-sm text-red-600">{err}</p>}
              {banner && (
                <div
                  className={`rounded-md border px-4 py-3 text-sm ${bannerClassName}`}
                  role="status"
                >
                  {banner.message}
                </div>
              )}
              <div className="space-y-2 text-sm text-slate-700">
                {currentAge !== null && dob && (
                  <p>
                    {t("pensionForecast.currentAge", { age: currentAge })} (
                    {t("pensionForecast.birthDate", { dob })})
                  </p>
                )}
                {retirementAge !== null && (
                  <p>{t("pensionForecast.retirementAge", { age: retirementAge })}</p>
                )}
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <ResultStat
                  label={t("pensionForecast.pensionPot")}
                  value={pensionPotDisplay}
                />
                {projectedPotLabel && projectedPotDisplay && (
                  <ResultStat label={projectedPotLabel} value={projectedPotDisplay} />
                )}
                {totalAnnualIncomeFormatted && (
                  <ResultStat
                    label={t("pensionForecast.totalAnnualIncome")}
                    value={totalAnnualIncomeFormatted}
                  />
                )}
                {totalMonthlyIncomeFormatted && (
                  <ResultStat
                    label={t("pensionForecast.totalMonthlyIncome")}
                    value={totalMonthlyIncomeFormatted}
                  />
                )}
              </div>
              {retirementIncomeBreakdown ? (
                <div className="overflow-x-auto">
                  <h3 className="mb-2 text-lg font-semibold text-slate-900">
                    {t("pensionForecast.incomeBreakdownHeading")}
                  </h3>
                  <table className="min-w-full divide-y divide-slate-200 text-sm">
                    <thead className="bg-slate-50">
                      <tr>
                        <th className="px-3 py-2 text-left font-semibold text-slate-700">
                          {t("pensionForecast.incomeTable.source")}
                        </th>
                        <th className="px-3 py-2 text-right font-semibold text-slate-700">
                          {t("pensionForecast.incomeTable.annual")}
                        </th>
                        <th className="px-3 py-2 text-right font-semibold text-slate-700">
                          {t("pensionForecast.incomeTable.monthly")}
                        </th>
                        <th className="px-3 py-2 text-right font-semibold text-slate-700">
                          {t("pensionForecast.incomeTable.share")}
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {breakdownEntries.map(({ key, label, annual, monthly, share }) => (
                        <tr key={String(key)} className="odd:bg-white even:bg-slate-50">
                          <td className="px-3 py-2 text-slate-700">{label}</td>
                          <td className="whitespace-nowrap px-3 py-2 text-right text-slate-900">
                            {currencyFormatter.format(annual)}
                          </td>
                          <td className="whitespace-nowrap px-3 py-2 text-right text-slate-900">
                            {currencyFormatter.format(monthly)}
                          </td>
                          <td className="whitespace-nowrap px-3 py-2 text-right text-slate-900">
                            {share}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                retirementIncomeTotal != null && (
                  <p className="text-sm text-slate-600">
                    {t("pensionForecast.prediction.noBreakdown")}
                  </p>
                )
              )}
            </div>
          </Panel>
        </div>
      </form>
      {data.length > 0 && (
        <div className="h-72 w-full rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data}>
              <XAxis dataKey="age" />
              <YAxis />
              <Tooltip />
              <Line type="monotone" dataKey="income" stroke="#1d4ed8" dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}

type PanelProps = {
  title: string;
  description?: string;
  children: ReactNode;
};

function Panel({ title, description, children }: PanelProps) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
      <header className="mb-4">
        <h2 className="text-xl font-semibold text-slate-900">{title}</h2>
        {description && (
          <p className="mt-1 text-sm text-slate-600">{description}</p>
        )}
      </header>
      <div className="space-y-5">{children}</div>
    </section>
  );
}

type SliderControlProps = {
  id: string;
  label: string;
  min: number;
  max: number;
  step?: number;
  value: number;
  onChange(value: number): void;
  valueFormatter?(value: number): string;
  helperText?: string;
  ariaValueText?: string;
};

function SliderControl({
  id,
  label,
  min,
  max,
  step,
  value,
  onChange,
  valueFormatter,
  helperText,
  ariaValueText,
}: SliderControlProps) {
  const formattedValue = valueFormatter ? valueFormatter(value) : String(value);
  const helperId = helperText ? `${id}-helper` : undefined;
  return (
    <div>
      <div className="flex items-center justify-between">
        <label htmlFor={id} className="text-sm font-medium text-slate-700">
          {label}
        </label>
        <span className="text-sm font-semibold text-slate-900">{formattedValue}</span>
      </div>
      {helperText && (
        <p id={helperId} className="mt-1 text-xs text-slate-500">
          {helperText}
        </p>
      )}
      <input
        id={id}
        type="range"
        min={min}
        max={max}
        step={step ?? 1}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
        aria-valuemin={min}
        aria-valuemax={max}
        aria-valuenow={value}
        aria-valuetext={ariaValueText ?? formattedValue}
        aria-describedby={helperId}
        className="mt-3 w-full accent-blue-600"
      />
    </div>
  );
}

type ResultStatProps = {
  label: string;
  value: string | null;
};

function ResultStat({ label, value }: ResultStatProps) {
  if (value == null) return null;
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-600">
        {label}
      </p>
      <p className="mt-1 text-lg font-semibold text-slate-900">{value}</p>
    </div>
  );
}
