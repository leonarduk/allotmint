import { type ChangeEvent, type ReactNode, useEffect, useMemo, useState } from "react";
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

type SliderFieldProps = {
  id: string;
  label: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  onChange: (value: number) => void;
  formatValue?: (value: number) => string;
  hint?: string;
};

function SliderField({
  id,
  label,
  value,
  min,
  max,
  step = 1,
  onChange,
  formatValue,
  hint,
}: SliderFieldProps) {
  const formattedValue = formatValue ? formatValue(value) : String(value);

  const handleChange = (event: ChangeEvent<HTMLInputElement>) => {
    onChange(Number(event.target.value));
  };

  return (
    <div className="space-y-2">
      <div className="flex items-baseline justify-between gap-3">
        <label htmlFor={id} className="text-sm font-medium text-gray-700">
          {label}
        </label>
        <span className="text-sm font-semibold text-gray-900" aria-live="polite">
          {formattedValue}
        </span>
      </div>
      <input
        id={id}
        type="range"
        className="w-full accent-blue-600"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={handleChange}
        aria-valuemin={min}
        aria-valuemax={max}
        aria-valuenow={value}
        aria-valuetext={formattedValue}
        {...(hint ? { "aria-describedby": `${id}-hint` } : {})}
      />
      {hint && (
        <p id={`${id}-hint`} className="text-xs text-gray-500">
          {hint}
        </p>
      )}
    </div>
  );
}

type CardProps = {
  title: string;
  description?: string;
  children: ReactNode;
};

function Card({ title, description, children }: CardProps) {
  return (
    <section className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
      <header className="mb-4 space-y-1">
        <h2 className="text-xl font-semibold text-gray-900">{title}</h2>
        {description && <p className="text-sm text-gray-600">{description}</p>}
      </header>
      <div className="space-y-5">{children}</div>
    </section>
  );
}

export default function PensionForecast() {
  const [owners, setOwners] = useState<OwnerSummary[]>([]);
  const [owner, setOwner] = useState("");
  const [deathAge, setDeathAge] = useState(90);
  const [statePension, setStatePension] = useState<string>("");
  const [monthlySavings, setMonthlySavings] = useState(500);
  const [monthlySpending, setMonthlySpending] = useState(2000);
  const { t } = useTranslation();

  const careerPathOptions = useMemo(
    () => [
      {
        key: "steady",
        label: t("pensionForecast.careerPath.options.steady"),
        description: t("pensionForecast.careerPath.descriptions.steady"),
        growth: 3,
      },
      {
        key: "balanced",
        label: t("pensionForecast.careerPath.options.balanced"),
        description: t("pensionForecast.careerPath.descriptions.balanced"),
        growth: 5,
      },
      {
        key: "accelerated",
        label: t("pensionForecast.careerPath.options.accelerated"),
        description: t("pensionForecast.careerPath.descriptions.accelerated"),
        growth: 7,
      },
    ],
    [t],
  );

  const [careerPathIndex, setCareerPathIndex] = useState(() => {
    const defaultIndex = careerPathOptions.findIndex((opt) => opt.growth === 5);
    return defaultIndex >= 0 ? defaultIndex : 0;
  });

  useEffect(() => {
    setCareerPathIndex((prev) => {
      const maxIndex = careerPathOptions.length - 1;
      return prev > maxIndex ? maxIndex : prev;
    });
  }, [careerPathOptions]);

  const investmentGrowthPct =
    careerPathOptions[careerPathIndex]?.growth ?? careerPathOptions[0].growth;

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
      const statePensionAnnual = statePension
        ? parseFloat(statePension)
        : undefined;
      const desiredIncomeAnnual = monthlySpending * 12;
      const res = await getPensionForecast({
        owner,
        deathAge,
        statePensionAnnual,
        contributionMonthly: monthlySavings,
        desiredIncomeAnnual,
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

  const desiredIncomeAnnualFormatted = currencyFormatter.format(
    monthlySpending * 12,
  );
  const desiredIncomeMonthlyFormatted = currencyFormatter.format(monthlySpending);
  const monthlySavingsFormatted = currencyFormatter.format(monthlySavings);
  const careerPathDescription =
    careerPathOptions[careerPathIndex]?.description ?? "";
  const careerPathLabel = careerPathOptions[careerPathIndex]?.label ?? "";

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold text-gray-900 md:text-4xl">
        {t("app.modes.pension")}
      </h1>
      <form onSubmit={handleSubmit} className="space-y-6">
        <div className="grid gap-6 lg:grid-cols-2">
          <Card
            title={t("pensionForecast.panels.now.title")}
            description={t("pensionForecast.panels.now.description")}
          >
            <OwnerSelector owners={owners} selected={owner} onSelect={setOwner} />
            <SliderField
              id="monthly-spending"
              label={t("pensionForecast.monthlySpending.label")}
              value={monthlySpending}
              min={500}
              max={6000}
              step={50}
              onChange={setMonthlySpending}
              formatValue={(val) => currencyFormatter.format(val)}
              hint={t("pensionForecast.monthlySpending.hint")}
            />
            <SliderField
              id="monthly-savings"
              label={t("pensionForecast.monthlySavings.label")}
              value={monthlySavings}
              min={0}
              max={3000}
              step={50}
              onChange={setMonthlySavings}
              formatValue={(val) => currencyFormatter.format(val)}
              hint={t("pensionForecast.monthlySavings.hint")}
            />
            <div className="rounded-lg border border-blue-100 bg-blue-50 p-4 text-sm text-blue-900">
              {t("pensionForecast.panels.now.summary", {
                spending: desiredIncomeMonthlyFormatted,
                savings: monthlySavingsFormatted,
              })}
            </div>
          </Card>
          <Card
            title={t("pensionForecast.panels.future.title")}
            description={t("pensionForecast.panels.future.description")}
          >
            <SliderField
              id="career-path"
              label={t("pensionForecast.careerPath.label")}
              value={careerPathIndex}
              min={0}
              max={careerPathOptions.length - 1}
              step={1}
              onChange={(val) => {
                const nextIndex = Math.round(val);
                setCareerPathIndex(nextIndex);
              }}
              formatValue={(val) => {
                const option = careerPathOptions[Math.round(val)];
                return option ? option.label : careerPathLabel;
              }}
              hint={careerPathDescription}
            />
            <div className="grid gap-4 sm:grid-cols-2">
              <label className="flex flex-col gap-2 text-sm font-medium text-gray-700" htmlFor="death-age">
                <span>{t("pensionForecast.deathAgeLabel")}</span>
                <input
                  id="death-age"
                  type="number"
                  min={0}
                  value={deathAge}
                  onChange={(e) => setDeathAge(Number(e.target.value))}
                  className="rounded-lg border border-gray-300 px-3 py-2 text-base shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/50"
                  required
                />
              </label>
              <label className="flex flex-col gap-2 text-sm font-medium text-gray-700" htmlFor="state-pension">
                <span>{t("pensionForecast.statePensionLabel")}</span>
                <div className="flex items-center gap-2">
                  <input
                    id="state-pension"
                    type="number"
                    min={0}
                    value={statePension}
                    onChange={(e) => setStatePension(e.target.value)}
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-base shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/50"
                  />
                  <span className="text-xs text-gray-500">£/yr</span>
                </div>
              </label>
            </div>
            <button
              type="submit"
              className="inline-flex items-center justify-center rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-blue-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
            >
              {t("pensionForecast.forecastCta")}
            </button>
            {err && <p className="text-sm text-red-600">{err}</p>}
            {banner && (
              <div
                className={`rounded-lg border px-4 py-3 text-sm ${bannerClassName}`}
                role="status"
              >
                {banner.message}
              </div>
            )}
            <div className="space-y-2 rounded-lg bg-gray-50 p-4 text-sm text-gray-700">
              <p className="font-semibold text-gray-900">
                {t("pensionForecast.futureSummary", {
                  career: careerPathLabel,
                  growth: percentFormatter.format(investmentGrowthPct / 100),
                })}
              </p>
              <p>
                {t("pensionForecast.plannedIncome", {
                  monthly: desiredIncomeMonthlyFormatted,
                  annual: desiredIncomeAnnualFormatted,
                })}
              </p>
              <p>
                {t("pensionForecast.monthlySavingsSummary", {
                  value: monthlySavingsFormatted,
                })}
              </p>
              {currentAge !== null && dob && (
                <p>
                  {t("pensionForecast.currentAge", { age: currentAge })} (
                  {t("pensionForecast.birthDate", { dob })})
                </p>
              )}
              {retirementAge !== null && (
                <p>{t("pensionForecast.retirementAge", { age: retirementAge })}</p>
              )}
              {pensionPot !== null && (
                <p>
                  {t("pensionForecast.pensionPot")}: £{pensionPot.toFixed(2)}
                </p>
              )}
              {projectedPot !== null && retirementAge !== null && (
                <p>
                  {t("pensionForecast.projectedPot", {
                    age: retirementAge,
                    value: currencyFormatter.format(projectedPot),
                  })}
                </p>
              )}
            </div>
            {retirementIncomeBreakdown && (
              <div className="space-y-3">
                <h3 className="text-lg font-semibold text-gray-900">
                  {t("pensionForecast.incomeBreakdownHeading")}
                </h3>
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-gray-200 text-sm">
                    <thead>
                      <tr className="bg-gray-50">
                        <th className="px-3 py-2 text-left font-semibold text-gray-700">
                          {t("pensionForecast.incomeTable.source")}
                        </th>
                        <th className="px-3 py-2 text-right font-semibold text-gray-700">
                          {t("pensionForecast.incomeTable.annual")}
                        </th>
                        <th className="px-3 py-2 text-right font-semibold text-gray-700">
                          {t("pensionForecast.incomeTable.monthly")}
                        </th>
                        <th className="px-3 py-2 text-right font-semibold text-gray-700">
                          {t("pensionForecast.incomeTable.share")}
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {breakdownEntries.map(({ key, label, annual, monthly, share }) => (
                        <tr key={String(key)} className="odd:bg-white even:bg-gray-50">
                          <td className="px-3 py-2">{label}</td>
                          <td className="whitespace-nowrap px-3 py-2 text-right">
                            {currencyFormatter.format(annual)}
                          </td>
                          <td className="whitespace-nowrap px-3 py-2 text-right">
                            {currencyFormatter.format(monthly)}
                          </td>
                          <td className="whitespace-nowrap px-3 py-2 text-right">
                            {share}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
            {!retirementIncomeBreakdown && retirementIncomeTotal != null && (
              <p className="text-sm text-gray-600">
                {t("pensionForecast.prediction.noBreakdown")}
              </p>
            )}
            {retirementIncomeTotal != null && (
              <div className="space-y-1 text-sm text-gray-800">
                <p>
                  {t("pensionForecast.totalAnnualIncome")}: {totalAnnualIncomeFormatted}
                </p>
                <p>
                  {t("pensionForecast.totalMonthlyIncome")}: {totalMonthlyIncomeFormatted}
                </p>
              </div>
            )}
            {data.length > 0 && (
              <div className="h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={data}>
                    <XAxis dataKey="age" />
                    <YAxis />
                    <Tooltip />
                    <Line
                      type="monotone"
                      dataKey="income"
                      stroke="#2563eb"
                      dot={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}
          </Card>
        </div>
      </form>
    </div>
  );
}
