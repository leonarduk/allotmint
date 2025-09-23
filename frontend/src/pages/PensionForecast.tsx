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

export default function PensionForecast() {
  const [owners, setOwners] = useState<OwnerSummary[]>([]);
  const [owner, setOwner] = useState("");
  const [deathAge, setDeathAge] = useState(90);
  const [statePension, setStatePension] = useState<string>("");
  const [contributionAnnual, setContributionAnnual] = useState<string>("");
  const [contributionMonthly, setContributionMonthly] = useState<string>("");
  const [employerContributionMonthly, setEmployerContributionMonthly] =
    useState<string>("");
  const [desiredIncome, setDesiredIncome] = useState<string>("");
  const [investmentGrowthPct, setInvestmentGrowthPct] = useState(5);
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
  const [additionalPensions, setAdditionalPensions] = useState<number>(0);
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

  const personalContributionMonthlyValue = useMemo(() => {
    if (contributionMonthly.trim() !== "") {
      const parsed = Number(contributionMonthly);
      return Number.isFinite(parsed) ? parsed : null;
    }
    if (contributionAnnual.trim() !== "") {
      const parsed = Number(contributionAnnual);
      if (Number.isFinite(parsed)) {
        return parsed / 12;
      }
    }
    return null;
  }, [contributionAnnual, contributionMonthly]);

  const employerContributionMonthlyValue = useMemo(() => {
    if (employerContributionMonthly.trim() === "") {
      return null;
    }
    const parsed = Number(employerContributionMonthly);
    return Number.isFinite(parsed) ? parsed : null;
  }, [employerContributionMonthly]);

  const totalContributionMonthlyValue = useMemo(() => {
    if (
      personalContributionMonthlyValue == null &&
      employerContributionMonthlyValue == null
    ) {
      return null;
    }
    return (
      (personalContributionMonthlyValue ?? 0) +
      (employerContributionMonthlyValue ?? 0)
    );
  }, [
    employerContributionMonthlyValue,
    personalContributionMonthlyValue,
  ]);

  const formatSummaryValue = (value: number | null) =>
    value != null
      ? currencyFormatter.format(value)
      : t("pensionForecast.summary.valueUnavailable");

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
      const contributionMonthlyVal = contributionMonthly
        ? parseFloat(contributionMonthly)
        : undefined;
      const contributionAnnualVal = contributionAnnual
        ? parseFloat(contributionAnnual)
        : undefined;
      const res = await getPensionForecast({
        owner,
        deathAge,
        statePensionAnnual: statePension
          ? parseFloat(statePension)
          : undefined,
        contributionMonthly: contributionMonthlyVal,
        contributionAnnual:
          contributionMonthlyVal !== undefined ? undefined : contributionAnnualVal,
        desiredIncomeAnnual: desiredIncome
          ? parseFloat(desiredIncome)
          : undefined,
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

  const handleAddAnotherPension = () => {
    setAdditionalPensions((count) => count + 1);
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
    <div>
      <h1 className="mb-4 text-2xl md:text-4xl">Pension Forecast</h1>
      <section
        aria-labelledby="pension-forecast-summary"
        className="mb-6 rounded-lg border border-gray-200 bg-white p-4 shadow-sm"
      >
        <h2 id="pension-forecast-summary" className="sr-only">
          {t("pensionForecast.summary.title")}
        </h2>
        <div className="flex flex-col gap-6 md:flex-row md:items-start md:justify-between">
          <div className="grid w-full grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <p className="text-sm font-medium text-gray-500">
                {t("pensionForecast.summary.pensionPotLabel")}
              </p>
              <p className="text-xl font-semibold text-gray-900">
                {formatSummaryValue(pensionPot)}
              </p>
            </div>
            <div>
              <p className="text-sm font-medium text-gray-500">
                {t("pensionForecast.summary.personalContributionLabel")}
              </p>
              <p className="text-xl font-semibold text-gray-900">
                {formatSummaryValue(personalContributionMonthlyValue)}
              </p>
            </div>
            <div>
              <p className="text-sm font-medium text-gray-500">
                {t("pensionForecast.summary.employerContributionLabel")}
              </p>
              <p className="text-xl font-semibold text-gray-900">
                {formatSummaryValue(employerContributionMonthlyValue)}
              </p>
            </div>
            {totalContributionMonthlyValue != null && (
              <div>
                <p className="text-sm font-medium text-gray-500">
                  {t("pensionForecast.summary.totalContributionLabel")}
                </p>
                <p className="text-xl font-semibold text-gray-900">
                  {currencyFormatter.format(totalContributionMonthlyValue)}
                </p>
              </div>
            )}
          </div>
          <div className="flex flex-col items-start gap-2 md:items-end">
            <button
              type="button"
              onClick={handleAddAnotherPension}
              className="rounded-md bg-blue-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-blue-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600"
            >
              {t("pensionForecast.summary.addAnotherPension")}
            </button>
            {additionalPensions > 0 && (
              <span className="text-sm text-gray-600">
                {t("pensionForecast.summary.additionalPensions", {
                  count: additionalPensions,
                })}
              </span>
            )}
          </div>
        </div>
      </section>
      <form onSubmit={handleSubmit} className="mb-4 space-y-2">
        <OwnerSelector owners={owners} selected={owner} onSelect={setOwner} />
        <div>
          <label className="mr-2">Death Age:</label>
          <input
            type="number"
            value={deathAge}
            onChange={(e) => setDeathAge(Number(e.target.value))}
            required
          />
        </div>
        <div>
          <label className="mr-2">State Pension (£/yr):</label>
          <input
            type="number"
            value={statePension}
            onChange={(e) => setStatePension(e.target.value)}
          />
        </div>
        <div>
          <label className="mr-2" htmlFor="contribution-annual">
            Annual Contribution (£):
          </label>
          <input
            id="contribution-annual"
            type="number"
            value={contributionAnnual}
            onChange={(e) => setContributionAnnual(e.target.value)}
          />
        </div>
        <div>
          <label className="mr-2" htmlFor="contribution-monthly">
            {t("pensionForecast.monthlyContribution")}
          </label>
          <input
            id="contribution-monthly"
            type="number"
            value={contributionMonthly}
            onChange={(e) => setContributionMonthly(e.target.value)}
          />
        </div>
        <div>
          <label className="mr-2" htmlFor="employer-contribution">
            {t("pensionForecast.employerContributionMonthly")}
          </label>
          <input
            id="employer-contribution"
            type="number"
            value={employerContributionMonthly}
            onChange={(e) => setEmployerContributionMonthly(e.target.value)}
          />
        </div>
        <div>
          <label className="mr-2" htmlFor="desired-income">
            Desired Income (£/yr):
          </label>
          <input
            id="desired-income"
            type="number"
            value={desiredIncome}
            onChange={(e) => setDesiredIncome(e.target.value)}
          />
        </div>
        <div>
          <label className="mr-2" htmlFor="investment-growth">
            {t("pensionForecast.growthAssumption")}
          </label>
          <select
            id="investment-growth"
            value={investmentGrowthPct}
            onChange={(e) => setInvestmentGrowthPct(Number(e.target.value))}
          >
            {[3, 5, 7].map((g) => (
              <option key={g} value={g}>
                {g}%
              </option>
            ))}
          </select>
        </div>
        <button type="submit" className="mt-2 rounded bg-blue-500 px-4 py-2 text-white">
          Forecast
        </button>
      </form>
      {err && <p className="text-red-500">{err}</p>}
      {banner && (
        <div
          className={`mb-4 rounded border px-4 py-3 text-sm ${bannerClassName}`}
          role="status"
        >
          {banner.message}
        </div>
      )}
      {currentAge !== null && dob && (
        <p className="mb-2">
          {t("pensionForecast.currentAge", { age: currentAge })} (
          {t("pensionForecast.birthDate", { dob })})
        </p>
      )}
      {retirementAge !== null && (
        <p className="mb-2">{t("pensionForecast.retirementAge", { age: retirementAge })}</p>
      )}
      {pensionPot !== null && (
        <p className="mb-2">
          {t("pensionForecast.pensionPot")}: £{pensionPot.toFixed(2)}
        </p>
      )}
      {projectedPot !== null && retirementAge !== null && (
        <p className="mb-2">
          Projected pot at {retirementAge}: £{projectedPot.toFixed(2)}
        </p>
      )}
      {retirementIncomeBreakdown && (
        <div className="mt-4 overflow-x-auto">
          <h2 className="mb-2 text-xl">
            {t("pensionForecast.incomeBreakdownHeading")}
          </h2>
          <table className="min-w-full divide-y divide-gray-200 text-sm">
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
                  <td className="whitespace-nowrap px-3 py-2 text-right">
                    {share}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {!retirementIncomeBreakdown && retirementIncomeTotal != null && (
        <p className="mt-4 text-sm text-gray-600">
          {t("pensionForecast.prediction.noBreakdown")}
        </p>
      )}
      {retirementIncomeTotal != null && (
        <div className="mt-2 text-sm">
          <p>
            {t("pensionForecast.totalAnnualIncome")}: {totalAnnualIncomeFormatted}
          </p>
          <p>
            {t("pensionForecast.totalMonthlyIncome")}: {totalMonthlyIncomeFormatted}
          </p>
        </div>
      )}
      {data.length > 0 && (
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={data}>
            <XAxis dataKey="age" />
            <YAxis />
            <Tooltip />
            <Line type="monotone" dataKey="income" stroke="#8884d8" dot={false} />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
