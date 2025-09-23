import { useEffect, useMemo, useState } from "react";
import {
  LineChart,
  Line,
  ResponsiveContainer,
  XAxis,
  YAxis,
  Tooltip,
} from "recharts";
import { getOwners, getPensionForecast } from "../api";
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
  const [employerContributionMonthly, setEmployerContributionMonthly] =
    useState<string>("");
  const [investmentGrowthPct, setInvestmentGrowthPct] = useState(5);
  const [data, setData] = useState<{ age: number; income: number }[]>([]);
  const [projectedPot, setProjectedPot] = useState<number | null>(null);
  const [pensionPot, setPensionPot] = useState<number | null>(null);
  const [currentAge, setCurrentAge] = useState<number | null>(null);
  const [retirementAge, setRetirementAge] = useState<number | null>(null);
  const [dob, setDob] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [additionalPensions, setAdditionalPensions] = useState<number>(0);
  const { t } = useTranslation();

  const parseNumberInput = (value: string): number | null => {
    if (!value.trim()) {
      return null;
    }
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  };

  const userMonthlyContributionValue = parseNumberInput(contributionMonthly);
  const employerMonthlyContributionValue = parseNumberInput(
    employerContributionMonthly,
  );

  const totalMonthlyContributionValue = useMemo(() => {
    if (
      userMonthlyContributionValue === null &&
      employerMonthlyContributionValue === null
    ) {
      return null;
    }
    return (
      (userMonthlyContributionValue ?? 0) +
      (employerMonthlyContributionValue ?? 0)
    );
  }, [userMonthlyContributionValue, employerMonthlyContributionValue]);

  const formatCurrency = (
    value: number | null | undefined,
    { allowDash = true }: { allowDash?: boolean } = {},
  ) => {
    if ((value === null || value === undefined) && allowDash) {
      return "—";
    }
    const amount = value ?? 0;
    return new Intl.NumberFormat("en-GB", {
      style: "currency",
      currency: "GBP",
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(amount);
  };

  const handleAddAnotherPension = () => {
    setAdditionalPensions((count) => count + 1);
  };

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
        totalMonthlyContributionValue === null
          ? undefined
          : totalMonthlyContributionValue;
      const contributionAnnualVal = (() => {
        const parsed = parseNumberInput(contributionAnnual);
        return parsed === null ? undefined : parsed;
      })();
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
      setErr(null);
    } catch (ex: any) {
      setErr(String(ex));
      setData([]);
    }
  };

  return (
    <div>
      <h1 className="mb-4 text-2xl md:text-4xl">Pension Forecast</h1>
      <section className="mb-6 rounded-lg bg-slate-50 p-4 shadow-sm">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div className="grid flex-1 gap-4 md:grid-cols-3">
            <div className="rounded-md bg-white p-4 shadow-inner">
              <p className="text-sm font-medium text-slate-500">
                {t("pensionForecast.pensionPot")}
              </p>
              <p
                className="mt-1 text-2xl font-semibold text-slate-900"
                data-testid="pension-pot-amount"
              >
                {formatCurrency(pensionPot)}
              </p>
            </div>
            <div className="rounded-md bg-white p-4 shadow-inner">
              <p className="text-sm font-medium text-slate-500">
                {t("pensionForecast.monthlyContributionHeader")}
              </p>
              <p
                className="mt-1 text-2xl font-semibold text-slate-900"
                data-testid="user-contribution-amount"
              >
                {formatCurrency(userMonthlyContributionValue, { allowDash: false })}
              </p>
            </div>
            <div className="rounded-md bg-white p-4 shadow-inner">
              <p className="text-sm font-medium text-slate-500">
                {t("pensionForecast.employerContributionHeader")}
              </p>
              <p
                className="mt-1 text-2xl font-semibold text-slate-900"
                data-testid="employer-contribution-amount"
              >
                {formatCurrency(employerMonthlyContributionValue, { allowDash: false })}
              </p>
            </div>
          </div>
          <div className="flex flex-col items-start gap-2">
            <button
              type="button"
              className="rounded-md border border-blue-500 px-4 py-2 text-sm font-medium text-blue-600 transition-colors hover:bg-blue-50"
              onClick={handleAddAnotherPension}
            >
              {t("pensionForecast.addAnotherPension")}
            </button>
            {additionalPensions > 0 && (
              <span className="text-xs text-blue-700" data-testid="additional-pension-notice">
                {t("pensionForecast.additionalPensionNotice", { count: additionalPensions })}
              </span>
            )}
            {totalMonthlyContributionValue !== null && (
              <span className="text-xs text-slate-500">
                {t("pensionForecast.totalMonthlyContribution", {
                  amount: formatCurrency(totalMonthlyContributionValue, { allowDash: false }),
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
          <label className="mr-2" htmlFor="employer-contribution-monthly">
            {t("pensionForecast.employerContributionInput")}
          </label>
          <input
            id="employer-contribution-monthly"
            type="number"
            value={employerContributionMonthly}
            onChange={(e) => setEmployerContributionMonthly(e.target.value)}
          />
        </div>
        <div>
          <label className="mr-2">Desired Income (£/yr):</label>
          <input
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
