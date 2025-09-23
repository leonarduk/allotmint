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
  const [desiredIncome, setDesiredIncome] = useState<string>("");
  const [investmentGrowthPct, setInvestmentGrowthPct] = useState(5);
  const [employerContributionMonthly, setEmployerContributionMonthly] =
    useState<string>("");
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
  const [monthlyContributionUsed, setMonthlyContributionUsed] = useState<
    number | null
  >(null);
  const [employerContributionMonthlyUsed, setEmployerContributionMonthlyUsed] =
    useState<number | null>(null);
  const [additionalPensionCount, setAdditionalPensionCount] = useState(0);
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

  const parseOptionalNumber = (value: string) => {
    if (value.trim() === "") {
      return undefined;
    }
    const parsed = Number(value);
    return Number.isNaN(parsed) ? undefined : parsed;
  };

  const handleAddAnotherPension = () => {
    setAdditionalPensionCount((count) => count + 1);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const contributionMonthlyVal = parseOptionalNumber(contributionMonthly);
      const contributionAnnualVal = parseOptionalNumber(contributionAnnual);
      const employerContributionMonthlyVal = parseOptionalNumber(
        employerContributionMonthly,
      );
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
      setMonthlyContributionUsed(
        contributionMonthlyVal !== undefined
          ? contributionMonthlyVal
          : contributionAnnualVal !== undefined
            ? contributionAnnualVal / 12
            : res.contribution_annual != null
              ? res.contribution_annual / 12
              : null,
      );
      setEmployerContributionMonthlyUsed(
        res.employer_contribution_monthly != null
          ? res.employer_contribution_monthly
          : employerContributionMonthlyVal ?? null,
      );
      setErr(null);
    } catch (ex: any) {
      setErr(String(ex));
      setData([]);
      setEarliestRetirementAge(null);
      setRetirementIncomeBreakdown(null);
      setRetirementIncomeTotal(null);
      setDesiredIncomeUsed(null);
      setMonthlyContributionUsed(null);
      setEmployerContributionMonthlyUsed(null);
    }
  };

  const contributionMonthlyNumber = parseOptionalNumber(contributionMonthly);
  const contributionAnnualNumber = parseOptionalNumber(contributionAnnual);
  const employerContributionMonthlyNumber = parseOptionalNumber(
    employerContributionMonthly,
  );

  const monthlyContributionDisplay =
    monthlyContributionUsed ??
    (contributionMonthlyNumber !== undefined
      ? contributionMonthlyNumber
      : contributionAnnualNumber !== undefined
        ? contributionAnnualNumber / 12
        : null);

  const employerContributionDisplay =
    employerContributionMonthlyUsed ??
    (employerContributionMonthlyNumber !== undefined
      ? employerContributionMonthlyNumber
      : null);

  const summaryItems = [
    {
      key: "pension-pot",
      label: t("pensionForecast.summary.pensionPotLabel"),
      value:
        pensionPot != null
          ? currencyFormatter.format(pensionPot)
          : "—",
    },
    {
      key: "user-contribution",
      label: t("pensionForecast.summary.userContributionLabel"),
      value:
        monthlyContributionDisplay != null
          ? currencyFormatter.format(monthlyContributionDisplay)
          : "—",
    },
    {
      key: "employer-contribution",
      label: t("pensionForecast.summary.employerContributionLabel"),
      value:
        employerContributionDisplay != null
          ? currencyFormatter.format(employerContributionDisplay)
          : "—",
    },
  ];

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
      <div className="mb-6 rounded-lg border border-slate-200 bg-slate-50 p-4 shadow-sm">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <h2 className="text-lg font-semibold">
              {t("pensionForecast.summary.heading")}
            </h2>
            <p className="text-sm text-slate-600">
              {t("pensionForecast.summary.addedPensions", {
                count: additionalPensionCount,
              })}
            </p>
          </div>
          <button
            type="button"
            className="inline-flex items-center justify-center rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
            onClick={handleAddAnotherPension}
          >
            {t("pensionForecast.summary.addAnotherPension")}
          </button>
        </div>
        <div className="mt-4 grid gap-4 md:grid-cols-3">
          {summaryItems.map((item) => (
            <div
              key={item.key}
              className="rounded border border-white bg-white px-4 py-3 shadow-sm"
            >
              <p className="text-sm text-slate-600">{item.label}</p>
              <p className="text-xl font-semibold">{item.value}</p>
            </div>
          ))}
        </div>
      </div>
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
          <label className="mr-2" htmlFor="employer-contribution-monthly">
            {t("pensionForecast.employerContributionMonthly")}
          </label>
          <input
            id="employer-contribution-monthly"
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
