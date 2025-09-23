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

type CareerPathOption = {
  label: string;
  description: string;
  growthPct: number;
};

const CAREER_PATH_OPTIONS: CareerPathOption[] = [
  {
    label: "Safety first",
    description: "Lower risk mix that prioritises capital preservation.",
    growthPct: 3,
  },
  {
    label: "Balanced climb",
    description: "Balanced portfolio blending growth and security.",
    growthPct: 5,
  },
  {
    label: "Accelerated growth",
    description: "Equity-heavy allocation aiming for faster growth.",
    growthPct: 7,
  },
];

type SliderControlProps = {
  id: string;
  label: string;
  min: number;
  max: number;
  step?: number;
  value: number;
  onChange: (value: number) => void;
  valueText: string;
  description?: string;
  marks?: { value: number; label: string }[];
};

function SliderControl({
  id,
  label,
  min,
  max,
  step = 1,
  value,
  onChange,
  valueText,
  description,
  marks,
}: SliderControlProps) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <label htmlFor={id} className="text-sm font-medium text-slate-700">
          {label}
        </label>
        <span className="text-sm font-semibold text-slate-900" aria-live="polite">
          {valueText}
        </span>
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
        aria-valuetext={valueText}
      />
      {description ? <p className="text-sm text-slate-500">{description}</p> : null}
      {marks ? (
        <div className="flex justify-between text-xs text-slate-500" aria-hidden="true">
          {marks.map((mark) => (
            <span key={mark.value}>{mark.label}</span>
          ))}
        </div>
      ) : null}
    </div>
  );
}

type StatProps = {
  label: string;
  value: string;
  helperText?: string;
};

function Stat({ label, value, helperText }: StatProps) {
  return (
    <div className="space-y-1 rounded-md bg-slate-50 p-3">
      <dt className="text-sm text-slate-600">{label}</dt>
      <dd className="text-lg font-semibold text-slate-900">{value}</dd>
      {helperText ? <p className="text-sm text-slate-500">{helperText}</p> : null}
    </div>
  );
}

export default function PensionForecast() {
  const [owners, setOwners] = useState<OwnerSummary[]>([]);
  const [owner, setOwner] = useState("");
  const [deathAge, setDeathAge] = useState(90);
  const [statePension, setStatePension] = useState<string>("");
  const [monthlySpending, setMonthlySpending] = useState(2500);
  const [monthlySavings, setMonthlySavings] = useState(600);
  const [careerPathIndex, setCareerPathIndex] = useState(1);
  const [data, setData] = useState<{ age: number; income: number }[]>([]);
  const [projectedPot, setProjectedPot] = useState<number | null>(null);
  const [pensionPot, setPensionPot] = useState<number | null>(null);
  const [currentAge, setCurrentAge] = useState<number | null>(null);
  const [retirementAge, setRetirementAge] = useState<number | null>(null);
  const [dob, setDob] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const { t } = useTranslation();
  const currencyFormatter = useMemo(
    () =>
      new Intl.NumberFormat("en-GB", {
        style: "currency",
        currency: "GBP",
        minimumFractionDigits: 0,
        maximumFractionDigits: 0,
      }),
    [],
  );
  const preciseCurrencyFormatter = useMemo(
    () =>
      new Intl.NumberFormat("en-GB", {
        style: "currency",
        currency: "GBP",
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
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
      const rawStatePension = statePension.trim();
      const statePensionAnnualVal =
        rawStatePension === "" ? undefined : Number(rawStatePension);
      const statePensionAnnual =
        statePensionAnnualVal !== undefined && !Number.isNaN(statePensionAnnualVal)
          ? statePensionAnnualVal
          : undefined;
      const investmentGrowthPct =
        CAREER_PATH_OPTIONS[careerPathIndex]?.growthPct ?? CAREER_PATH_OPTIONS[1].growthPct;
      const res = await getPensionForecast({
        owner,
        deathAge,
        statePensionAnnual,
        contributionMonthly: monthlySavings,
        desiredIncomeAnnual: monthlySpending * 12,
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

  const selectedCareerPath =
    CAREER_PATH_OPTIONS[careerPathIndex] ?? CAREER_PATH_OPTIONS[1];
  const desiredIncomeAnnual = monthlySpending * 12;
  const statePensionAnnual =
    statePension.trim() === "" ? undefined : Number(statePension);
  const normalizedStatePensionAnnual =
    statePensionAnnual !== undefined && !Number.isNaN(statePensionAnnual)
      ? statePensionAnnual
      : undefined;
  const statePensionMonthly =
    normalizedStatePensionAnnual !== undefined
      ? normalizedStatePensionAnnual / 12
      : null;
  const formatCurrency = (value: number) => currencyFormatter.format(Math.round(value));
  const formatPreciseCurrency = (value: number) => preciseCurrencyFormatter.format(value);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl md:text-4xl">Pension Forecast</h1>
      <form
        onSubmit={handleSubmit}
        className="grid gap-6 md:grid-cols-2"
        aria-labelledby="pension-forecast-now pension-forecast-future"
      >
        <section
          className="flex flex-col gap-6 rounded-lg border border-slate-200 bg-white p-6 shadow-sm"
          aria-labelledby="pension-forecast-now"
        >
          <div>
            <h2 id="pension-forecast-now" className="text-xl font-semibold text-slate-900">
              Now
            </h2>
            <p className="mt-1 text-sm text-slate-600">
              Tune the assumptions that describe your current plan.
            </p>
          </div>
          <div className="space-y-4">
            <OwnerSelector owners={owners} selected={owner} onSelect={setOwner} />
            <div className="grid gap-4 sm:grid-cols-2">
              <label className="flex flex-col gap-1 text-sm font-medium text-slate-700">
                <span>Death age</span>
                <input
                  type="number"
                  value={deathAge}
                  onChange={(e) => setDeathAge(Number(e.target.value))}
                  required
                  className="rounded border border-slate-300 px-3 py-2 text-base"
                />
              </label>
              <label className="flex flex-col gap-1 text-sm font-medium text-slate-700">
                <span>State pension (£/year)</span>
                <input
                  type="number"
                  value={statePension}
                  onChange={(e) => setStatePension(e.target.value)}
                  className="rounded border border-slate-300 px-3 py-2 text-base"
                />
              </label>
            </div>
            <SliderControl
              id="career-path"
              label="Career path"
              min={0}
              max={CAREER_PATH_OPTIONS.length - 1}
              step={1}
              value={careerPathIndex}
              onChange={setCareerPathIndex}
              valueText={`${selectedCareerPath.label} (${selectedCareerPath.growthPct}%)`}
              description={selectedCareerPath.description}
              marks={CAREER_PATH_OPTIONS.map((option, index) => ({
                value: index,
                label: option.label,
              }))}
            />
            <SliderControl
              id="monthly-spending"
              label="Monthly spending"
              min={500}
              max={10000}
              step={100}
              value={monthlySpending}
              onChange={setMonthlySpending}
              valueText={`${formatCurrency(monthlySpending)}/mo`}
              description={`That's ${formatCurrency(desiredIncomeAnnual)} per year.`}
            />
            <SliderControl
              id="monthly-savings"
              label={t("pensionForecast.monthlyContribution")}
              min={0}
              max={5000}
              step={50}
              value={monthlySavings}
              onChange={setMonthlySavings}
              valueText={`${formatCurrency(monthlySavings)}/mo`}
              description="How much you invest every month until retirement."
            />
          </div>
          <div className="flex items-center justify-between gap-4">
            {err ? <p className="text-sm text-red-500">{err}</p> : <span />}
            <button
              type="submit"
              className="rounded bg-blue-500 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-blue-600"
            >
              Forecast
            </button>
          </div>
        </section>
        <section
          className="flex flex-col gap-6 rounded-lg border border-slate-200 bg-white p-6 shadow-sm"
          aria-labelledby="pension-forecast-future"
        >
          <div>
            <h2 id="pension-forecast-future" className="text-xl font-semibold text-slate-900">
              Future you
            </h2>
            <p className="mt-1 text-sm text-slate-600">
              Preview the lifestyle your savings could support.
            </p>
          </div>
          <dl className="grid gap-3">
            <Stat
              label="Retirement income target"
              value={`${formatCurrency(monthlySpending)}/mo`}
              helperText={`Equivalent to ${formatCurrency(desiredIncomeAnnual)} each year.`}
            />
            <Stat
              label="Monthly savings"
              value={`${formatCurrency(monthlySavings)}/mo`}
              helperText="Automatically contributed into your pension."
            />
            <Stat
              label="Career path"
              value={selectedCareerPath.label}
              helperText={`Assumes ${selectedCareerPath.growthPct}% annual investment growth.`}
            />
            {statePensionMonthly !== null ? (
              <Stat
                label="Estimated state pension"
                value={`${formatCurrency(statePensionMonthly)}/mo`}
                helperText={`About ${formatCurrency(normalizedStatePensionAnnual!)} annually.`}
              />
            ) : null}
            {pensionPot !== null ? (
              <Stat
                label={t("pensionForecast.pensionPot")}
                value={formatPreciseCurrency(pensionPot)}
              />
            ) : null}
            {projectedPot !== null && retirementAge !== null ? (
              <Stat
                label={`Projected pot at ${retirementAge}`}
                value={formatPreciseCurrency(projectedPot)}
              />
            ) : null}
          </dl>
          {currentAge !== null && dob ? (
            <p className="text-sm text-slate-700">
              {t("pensionForecast.currentAge", { age: currentAge })} (
              {t("pensionForecast.birthDate", { dob })})
            </p>
          ) : null}
          {retirementAge !== null ? (
            <p className="text-sm text-slate-700">
              {t("pensionForecast.retirementAge", { age: retirementAge })}
            </p>
          ) : null}
          {data.length > 0 ? (
            <ResponsiveContainer width="100%" height={240}>
              <LineChart data={data}>
                <XAxis dataKey="age" />
                <YAxis />
                <Tooltip />
                <Line type="monotone" dataKey="income" stroke="#8884d8" dot={false} />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-sm text-slate-500">
              Adjust the controls and run the forecast to see how your income evolves over time.
            </p>
          )}
        </section>
      </form>
    </div>
  );
}
