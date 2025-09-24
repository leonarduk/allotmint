import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
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
import { useRoute } from "../RouteContext";
import { sanitizeOwners } from "../utils/owners";

export default function PensionForecast() {
  const [owners, setOwners] = useState<OwnerSummary[]>([]);
  const { selectedOwner, setSelectedOwner } = useRoute();
  const [owner, setOwner] = useState("");
  const [deathAge, setDeathAge] = useState(90);
  const [statePension, setStatePension] = useState<string>("");
  const [monthlySavings, setMonthlySavings] = useState(250);
  const [monthlySpending, setMonthlySpending] = useState(2000);
  const [employerContributionMonthly, setEmployerContributionMonthly] =
    useState(150);
  const [additionalPensions, setAdditionalPensions] = useState(0);
  const [careerPathIndex, setCareerPathIndex] = useState(1);
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

  const totalMonthlyContribution = monthlySavings + employerContributionMonthly;

  const handleAddAnotherPension = () => {
    setAdditionalPensions((count) => count + 1);
  };

  useEffect(() => {
    getOwners()
      .then((os) => {
        setOwners(sanitizeOwners(os));
      })
      .catch(() => setOwners([]));
  }, []);

  useEffect(() => {
    if (!owners.length) return;

    if (selectedOwner && owners.some((o) => o.owner === selectedOwner)) {
      setOwner(selectedOwner);
      return;
    }

    const fallbackOwner = owners.find((o) => o.owner !== "demo") ?? owners[0];
    if (!fallbackOwner) return;

    setOwner(fallbackOwner.owner);
    setSelectedOwner(fallbackOwner.owner);
  }, [owners, selectedOwner, setSelectedOwner]);

  const careerPathOptions = [
    {
      id: "steady",
      label: "Steady climb",
      helper: "Lower growth assumption",
      investmentGrowthPct: 3,
    },
    {
      id: "balanced",
      label: "Balanced pace",
      helper: "Moderate long-term growth",
      investmentGrowthPct: 5,
    },
    {
      id: "accelerated",
      label: "Accelerated path",
      helper: "Higher-risk, higher-reward growth",
      investmentGrowthPct: 7,
    },
  ] as const;

  const selectedCareerPath =
    careerPathOptions[careerPathIndex] ?? careerPathOptions[1];

  const handleSelectOwner = (value: string) => {
    setOwner(value);
    setSelectedOwner(value);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await getPensionForecast({
        owner,
        deathAge,
        statePensionAnnual: statePension
          ? parseFloat(statePension)
          : undefined,
        contributionMonthly: monthlySavings,
        desiredIncomeAnnual: monthlySpending * 12,
        investmentGrowthPct: selectedCareerPath.investmentGrowthPct,
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

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <h1 className="text-2xl md:text-4xl">Pension Forecast</h1>
      <section
        aria-labelledby="pension-snapshot-heading"
        className="rounded-3xl bg-slate-900 p-6 text-white shadow-sm"
      >
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div className="space-y-1">
            <p className="text-xs font-semibold uppercase tracking-wide text-blue-200">
              {t("pensionForecast.header.kicker")}
            </p>
            <h2
              id="pension-snapshot-heading"
              className="text-2xl font-semibold md:text-3xl"
            >
              {t("pensionForecast.header.heading")}
            </h2>
            {additionalPensions > 0 && (
              <p className="text-sm text-blue-100">
                {t("pensionForecast.header.additionalPensions", {
                  count: additionalPensions,
                })}
              </p>
            )}
          </div>
          <button
            type="button"
            onClick={handleAddAnotherPension}
            className="inline-flex items-center justify-center rounded-full border border-white/30 px-4 py-2 text-sm font-semibold text-white transition hover:border-white hover:bg-white hover:text-slate-900 focus:outline-none focus:ring-2 focus:ring-white/60 focus:ring-offset-2 focus:ring-offset-slate-900"
          >
            {t("pensionForecast.header.addAnother")}
          </button>
        </div>
        <dl className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <SnapshotStat
            label={t("pensionForecast.header.pensionPot")}
            value={
              pensionPot != null
                ? currencyFormatter.format(pensionPot)
                : t("pensionForecast.header.notAvailable")
            }
          />
          <SnapshotStat
            label={t("pensionForecast.header.employeeContribution")}
            value={currencyFormatter.format(monthlySavings)}
          />
          <SnapshotStat
            label={t("pensionForecast.header.employerContribution")}
            value={currencyFormatter.format(employerContributionMonthly)}
            helper={t("pensionForecast.header.totalContribution", {
              total: currencyFormatter.format(totalMonthlyContribution),
            })}
          />
        </dl>
      </section>
      <div className="grid gap-6 md:grid-cols-2">
        <section
          className="flex h-full flex-col gap-6 rounded-3xl border border-slate-200 bg-white p-6 shadow-sm"
          aria-labelledby="pension-now-heading"
        >
          <header className="space-y-2">
            <p className="text-sm font-semibold uppercase tracking-wide text-slate-500">
              Now
            </p>
            <h2 id="pension-now-heading" className="text-2xl font-semibold text-slate-900">
              Adjust the plan to match your life today
            </h2>
            <p className="text-sm text-slate-600">
              Move the sliders to see how changes to your savings and spending affect your retirement outlook.
            </p>
          </header>
          <div className="space-y-5">
            <OwnerSelector
              owners={owners}
              selected={owner}
              onSelect={handleSelectOwner}
            />
            <SliderControl
              id="career-path"
              label="Career path"
              min={0}
              max={careerPathOptions.length - 1}
              step={1}
              value={careerPathIndex}
              onChange={(value) => setCareerPathIndex(value)}
              formatValue={(value) => {
                const option = careerPathOptions[value] ?? selectedCareerPath;
                return `${option.label} (${option.investmentGrowthPct}%)`;
              }}
              getValueText={(value) =>
                careerPathOptions[value]?.label ?? selectedCareerPath.label
              }
              marks={careerPathOptions.map((option, index) => ({
                value: index,
                label: option.label,
              }))}
              helper={selectedCareerPath.helper}
            />
            <SliderControl
              id="monthly-savings"
              label="Monthly savings"
              min={0}
              max={2000}
              step={50}
              value={monthlySavings}
              onChange={(value) => setMonthlySavings(value)}
              formatValue={(value) => currencyFormatter.format(value)}
              getValueText={(value) => currencyFormatter.format(value)}
            />
            <SliderControl
              id="employer-contribution"
              label={t("pensionForecast.employerContributionLabel")}
              min={0}
              max={2000}
              step={50}
              value={employerContributionMonthly}
              onChange={(value) => setEmployerContributionMonthly(value)}
              formatValue={(value) => currencyFormatter.format(value)}
              getValueText={(value) => currencyFormatter.format(value)}
            />
            <SliderControl
              id="monthly-spending"
              label="Monthly spending in retirement"
              min={500}
              max={6000}
              step={50}
              value={monthlySpending}
              onChange={(value) => setMonthlySpending(value)}
              formatValue={(value) => currencyFormatter.format(value)}
              getValueText={(value) => currencyFormatter.format(value)}
            />
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <label className="block text-sm font-medium text-slate-700" htmlFor="death-age">
                  Death age
                </label>
                <input
                  id="death-age"
                  type="number"
                  className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-slate-500 focus:outline-none focus:ring-2 focus:ring-slate-200"
                  value={deathAge}
                  onChange={(e) => setDeathAge(Number(e.target.value))}
                  required
                  min={50}
                  max={120}
                />
              </div>
              <div className="space-y-2">
                <label className="block text-sm font-medium text-slate-700" htmlFor="state-pension">
                  State pension (£/yr)
                </label>
                <input
                  id="state-pension"
                  type="number"
                  className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-slate-500 focus:outline-none focus:ring-2 focus:ring-slate-200"
                  value={statePension}
                  onChange={(e) => setStatePension(e.target.value)}
                  min={0}
                />
              </div>
            </div>
          </div>
          <div className="flex items-center justify-end">
            <button
              type="submit"
              className="rounded-full bg-blue-600 px-5 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-400 focus:ring-offset-2"
            >
              Forecast
            </button>
          </div>
        </section>
        <section
          className="flex h-full flex-col gap-4 rounded-3xl border border-slate-200 bg-slate-50 p-6"
          aria-labelledby="pension-future-heading"
        >
          <header className="space-y-1">
            <p className="text-sm font-semibold uppercase tracking-wide text-slate-500">
              Future you
            </p>
            <h2 id="pension-future-heading" className="text-2xl font-semibold text-slate-900">
              See what retirement could look like
            </h2>
          </header>
          {err && <p className="text-sm text-red-600">{err}</p>}
          {banner && (
            <div
              className={`rounded-2xl border px-4 py-3 text-sm ${bannerClassName}`}
              role="status"
            >
              {banner.message}
            </div>
          )}
          <div className="space-y-3 text-sm text-slate-700">
            {currentAge !== null && dob && (
              <InfoLine
                label={t("pensionForecast.currentAge", { age: currentAge })}
                value={t("pensionForecast.birthDate", { dob })}
              />
            )}
            {retirementAge !== null && (
              <InfoLine
                label={t("pensionForecast.retirementAge", { age: retirementAge })}
              />
            )}
            {pensionPot !== null && (
              <InfoLine
                label={t("pensionForecast.pensionPot")}
                value={currencyFormatter.format(pensionPot)}
              />
            )}
            {projectedPot !== null && retirementAge !== null && (
              <InfoLine
                label={`Projected pot at ${retirementAge}`}
                value={currencyFormatter.format(projectedPot)}
              />
            )}
          </div>
          {retirementIncomeBreakdown && (
            <div className="overflow-x-auto rounded-2xl bg-white p-4 shadow-sm">
              <h3 className="mb-3 text-lg font-semibold text-slate-900">
                {t("pensionForecast.incomeBreakdownHeading")}
              </h3>
              <table className="min-w-full divide-y divide-slate-200 text-sm">
                <thead>
                  <tr className="bg-slate-100 text-left">
                    <th className="px-3 py-2 font-semibold text-slate-700">
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
          )}
          {!retirementIncomeBreakdown && retirementIncomeTotal != null && (
            <p className="rounded-2xl bg-white p-4 text-sm text-slate-600 shadow-sm">
              {t("pensionForecast.prediction.noBreakdown")}
            </p>
          )}
          {retirementIncomeTotal != null && (
            <div className="rounded-2xl bg-white p-4 text-sm shadow-sm">
              <p className="font-medium text-slate-900">
                {t("pensionForecast.totalAnnualIncome")}: {totalAnnualIncomeFormatted}
              </p>
              <p className="text-slate-700">
                {t("pensionForecast.totalMonthlyIncome")}: {totalMonthlyIncomeFormatted}
              </p>
            </div>
          )}
          {data.length > 0 && (
            <div className="h-72 rounded-2xl bg-white p-4 shadow-sm">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={data}>
                  <XAxis dataKey="age" />
                  <YAxis />
                  <Tooltip />
                  <Line type="monotone" dataKey="income" stroke="#2563eb" dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </section>
      </div>
    </form>
  );
}

type SliderControlProps = {
  id: string;
  label: string;
  min: number;
  max: number;
  step?: number;
  value: number;
  onChange: (value: number) => void;
  formatValue?: (value: number) => string;
  getValueText?: (value: number) => string;
  marks?: Array<{ value: number; label: string }>;
  helper?: string;
};

function SnapshotStat({
  label,
  value,
  helper,
}: {
  label: string;
  value: string;
  helper?: string;
}) {
  return (
    <div className="rounded-2xl bg-white/10 p-4">
      <dt className="text-sm font-medium text-blue-100">{label}</dt>
      <dd className="mt-2 text-2xl font-semibold">{value}</dd>
      {helper && <p className="mt-1 text-xs text-blue-100">{helper}</p>}
    </div>
  );
}

function SliderControl({
  id,
  label,
  min,
  max,
  step = 1,
  value,
  onChange,
  formatValue,
  getValueText,
  marks,
  helper,
}: SliderControlProps) {
  const descriptionId = helper ? `${id}-description` : undefined;
  const displayValue = formatValue ? formatValue(value) : String(value);
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-3">
        <label className="text-sm font-medium text-slate-700" htmlFor={id}>
          {label}
        </label>
        <span className="text-sm font-semibold text-slate-900">{displayValue}</span>
      </div>
      <input
        id={id}
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
        className="w-full accent-blue-600"
        aria-valuetext={getValueText ? getValueText(value) : undefined}
        aria-describedby={descriptionId}
      />
      {marks && marks.length > 0 && (
        <div className="flex justify-between text-xs text-slate-500">
          {marks.map((mark) => (
            <span key={`${id}-${mark.value}`}>{mark.label}</span>
          ))}
        </div>
      )}
      {helper && (
        <p id={descriptionId} className="text-xs text-slate-500">
          {helper}
        </p>
      )}
    </div>
  );
}

function InfoLine({
  label,
  value,
}: {
  label: string;
  value?: ReactNode;
}) {
  return (
    <div className="rounded-xl bg-white p-3 shadow-sm">
      <p className="text-sm font-medium text-slate-900">{label}</p>
      {value && <p className="text-xs text-slate-600">{value}</p>}
    </div>
  );
}
