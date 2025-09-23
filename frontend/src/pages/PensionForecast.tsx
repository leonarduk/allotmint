import { useEffect, useMemo, useState } from "react";
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

type SliderControlProps = {
  id: string;
  label: string;
  min: number;
  max: number;
  step: number;
  value: number;
  onChange: (value: number) => void;
  formatValue?: (value: number) => string;
  description?: string;
};

function SliderControl({
  id,
  label,
  min,
  max,
  step,
  value,
  onChange,
  formatValue,
  description,
}: SliderControlProps) {
  const formatted = formatValue ? formatValue(value) : String(value);

  return (
    <div>
      <div className="flex items-baseline justify-between gap-4">
        <label htmlFor={id} className="text-sm font-medium text-gray-900">
          {label}
        </label>
        <span className="text-sm text-gray-600" data-testid={`${id}-value`}>
          {formatted}
        </span>
      </div>
      {description && (
        <p id={`${id}-description`} className="mt-1 text-xs text-gray-500">
          {description}
        </p>
      )}
      <input
        id={id}
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        aria-describedby={description ? `${id}-description` : undefined}
        aria-valuetext={formatted}
        onChange={(event) => onChange(Number(event.target.value))}
        className="mt-3 w-full accent-blue-600"
      />
    </div>
  );
}

export default function PensionForecast() {
  const [owners, setOwners] = useState<OwnerSummary[]>([]);
  const [owner, setOwner] = useState("");
  const [deathAge, setDeathAge] = useState(90);
  const [statePension, setStatePension] = useState<string>("");
  const [careerPathIndex, setCareerPathIndex] = useState(1);
  const [monthlySpending, setMonthlySpending] = useState(2000);
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

  const formatMonthlyValue = (value: number) =>
    `${currencyFormatter.format(value)} ${t("pensionForecast.perMonthSuffix")}`;

  const careerPathOptions = useMemo(
    () => [
      {
        value: 0,
        label: t("pensionForecast.careerPath.emerging"),
        description: t("pensionForecast.careerPath.emergingDescription"),
        growthPct: 3,
      },
      {
        value: 1,
        label: t("pensionForecast.careerPath.steady"),
        description: t("pensionForecast.careerPath.steadyDescription"),
        growthPct: 5,
      },
      {
        value: 2,
        label: t("pensionForecast.careerPath.accelerating"),
        description: t("pensionForecast.careerPath.acceleratingDescription"),
        growthPct: 7,
      },
    ],
    [t],
  );

  const boundedCareerIndex = Math.min(
    Math.max(careerPathIndex, 0),
    Math.max(careerPathOptions.length - 1, 0),
  );
  const selectedCareerPath = careerPathOptions[boundedCareerIndex] ?? careerPathOptions[0];
  const investmentGrowthPct = selectedCareerPath?.growthPct ?? 5;
  const contributionMonthlyValue = Number.isFinite(monthlySavings)
    ? monthlySavings
    : undefined;
  const desiredIncomeAnnualValue = Number.isFinite(monthlySpending)
    ? monthlySpending * 12
    : undefined;

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
      const res = await getPensionForecast({
        owner,
        deathAge,
        statePensionAnnual: statePension
          ? parseFloat(statePension)
          : undefined,
        contributionMonthly: contributionMonthlyValue,
        desiredIncomeAnnual: desiredIncomeAnnualValue,
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

  const highlightMetrics: Array<{ label: string; value: string }> = [];
  if (totalMonthlyIncomeFormatted) {
    highlightMetrics.push({
      label: t("pensionForecast.totalMonthlyIncome"),
      value: totalMonthlyIncomeFormatted,
    });
  }
  if (totalAnnualIncomeFormatted) {
    highlightMetrics.push({
      label: t("pensionForecast.totalAnnualIncome"),
      value: totalAnnualIncomeFormatted,
    });
  }
  if (desiredIncomeUsed != null) {
    highlightMetrics.push({
      label: t("pensionForecast.desiredIncomeGoal"),
      value: currencyFormatter.format(desiredIncomeUsed),
    });
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl md:text-4xl">Pension Forecast</h1>
      <div className="grid gap-6 lg:grid-cols-2">
        <form
          onSubmit={handleSubmit}
          className="flex flex-col gap-6 rounded-xl border border-gray-200 bg-white p-6 shadow-sm"
          aria-labelledby="pension-now-heading"
        >
          <div>
            <h2 id="pension-now-heading" className="text-xl font-semibold text-gray-900">
              {t("pensionForecast.nowHeading")}
            </h2>
            <p className="mt-1 text-sm text-gray-600">{t("pensionForecast.nowIntro")}</p>
          </div>
          <OwnerSelector owners={owners} selected={owner} onSelect={setOwner} />
          <SliderControl
            id="career-path"
            label={t("pensionForecast.careerPath.label")}
            min={0}
            max={Math.max(careerPathOptions.length - 1, 0)}
            step={1}
            value={boundedCareerIndex}
            onChange={(value) => setCareerPathIndex(Math.round(value))}
            formatValue={(value) => {
              const option = careerPathOptions[Math.round(value)] ?? careerPathOptions[0];
              return option ? option.label : "";
            }}
            description={selectedCareerPath?.description}
          />
          <p className="text-xs text-gray-500">
            {t("pensionForecast.growthAssumptionValue", { value: investmentGrowthPct })}
          </p>
          <SliderControl
            id="monthly-spending"
            label={t("pensionForecast.monthlySpendingLabel")}
            min={0}
            max={10000}
            step={50}
            value={monthlySpending}
            onChange={setMonthlySpending}
            formatValue={formatMonthlyValue}
          />
          <SliderControl
            id="monthly-savings"
            label={t("pensionForecast.monthlySavingsLabel")}
            min={0}
            max={5000}
            step={50}
            value={monthlySavings}
            onChange={setMonthlySavings}
            formatValue={formatMonthlyValue}
          />
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-2">
              <label htmlFor="death-age" className="text-sm font-medium text-gray-900">
                {t("pensionForecast.deathAgeLabel")}
              </label>
              <input
                id="death-age"
                type="number"
                className="rounded border border-gray-300 px-3 py-2"
                value={deathAge}
                onChange={(e) => setDeathAge(Number(e.target.value))}
                min={0}
                required
              />
            </div>
            <div className="flex flex-col gap-2">
              <label htmlFor="state-pension" className="text-sm font-medium text-gray-900">
                {t("pensionForecast.statePensionLabel")}
              </label>
              <input
                id="state-pension"
                type="number"
                className="rounded border border-gray-300 px-3 py-2"
                value={statePension}
                onChange={(e) => setStatePension(e.target.value)}
                min={0}
              />
            </div>
          </div>
          <button
            type="submit"
            className="self-start rounded bg-blue-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-blue-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600"
          >
            {t("pensionForecast.forecastCta")}
          </button>
        </form>
        <section
          className="flex flex-col gap-6 rounded-xl border border-gray-200 bg-white p-6 shadow-sm"
          aria-labelledby="pension-future-heading"
        >
          <div>
            <h2 id="pension-future-heading" className="text-xl font-semibold text-gray-900">
              {t("pensionForecast.futureHeading")}
            </h2>
            <p className="mt-1 text-sm text-gray-600">{t("pensionForecast.futureIntro")}</p>
          </div>
          {err && <p className="text-sm text-red-600">{err}</p>}
          {banner && (
            <div className={`rounded border px-4 py-3 text-sm ${bannerClassName}`} role="status">
              {banner.message}
            </div>
          )}
          {highlightMetrics.length > 0 && (
            <dl className="grid gap-4 sm:grid-cols-2">
              {highlightMetrics.map(({ label, value }) => (
                <div key={label} className="rounded-lg bg-gray-50 p-4">
                  <dt className="text-sm text-gray-600">{label}</dt>
                  <dd className="mt-1 text-2xl font-semibold text-gray-900">{value}</dd>
                </div>
              ))}
            </dl>
          )}
          <div className="space-y-2 text-sm text-gray-700">
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
                {t("pensionForecast.pensionPot")}: {currencyFormatter.format(pensionPot)}
              </p>
            )}
            {projectedPot !== null && retirementAge !== null && (
              <p>
                {t("pensionForecast.projectedPotAtAge", {
                  age: retirementAge,
                  total: currencyFormatter.format(projectedPot),
                })}
              </p>
            )}
          </div>
          {retirementIncomeBreakdown && (
            <div className="overflow-x-auto text-sm">
              <h3 className="mb-2 text-lg font-semibold text-gray-900">
                {t("pensionForecast.incomeBreakdownHeading")}
              </h3>
              <table className="min-w-full divide-y divide-gray-200">
                <thead>
                  <tr className="bg-gray-50">
                    <th className="px-3 py-2 text-left font-semibold">
                      {t("pensionForecast.incomeTable.source")}
                    </th>
                    <th className="px-3 py-2 text-right font-semibold">
                      {t("pensionForecast.incomeTable.annual")}
                    </th>
                    <th className="px-3 py-2 text-right font-semibold">
                      {t("pensionForecast.incomeTable.monthly")}
                    </th>
                    <th className="px-3 py-2 text-right font-semibold">
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
                      <td className="whitespace-nowrap px-3 py-2 text-right">{share}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {!retirementIncomeBreakdown && retirementIncomeTotal != null && (
            <p className="text-sm text-gray-600">
              {t("pensionForecast.prediction.noBreakdown")}
            </p>
          )}
          {data.length > 0 ? (
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={data}>
                  <XAxis dataKey="age" />
                  <YAxis />
                  <Tooltip />
                  <Line type="monotone" dataKey="income" stroke="#8884d8" dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          ) : (
            retirementIncomeTotal == null &&
            !retirementIncomeBreakdown &&
            !err && (
              <p className="text-sm text-gray-500">
                {t("pensionForecast.futurePlaceholder")}
              </p>
            )
          )}
        </section>
      </div>
    </div>
  );
}
