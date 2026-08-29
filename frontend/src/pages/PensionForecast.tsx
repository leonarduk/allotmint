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
  getPortfolio,
  type PensionIncomeBreakdown,
} from "../api";
import type { OwnerSummary } from "../types";
import { useTranslation } from "react-i18next";
import { useRoute } from "../RouteContext";
import { sanitizeOwners } from "../utils/owners";
import { accountTypeLabel, isPensionAccountType } from "../utils/accountTypes";

export default function PensionForecast() {
  const [owners, setOwners] = useState<OwnerSummary[]>([]);
  const { selectedOwner, setSelectedOwner } = useRoute();
  const [owner, setOwner] = useState("");
  const [deathAge, setDeathAge] = useState(90);
  // Defaults to "0" (not blank) so the field always shows a concrete starting
  // value per #7211. This intentionally reproduces the *existing* behaviour:
  // an empty field was already sent as `undefined`, which the backend treats
  // as 0 income from state pension (see backend/routes/pension.py). Making
  // that explicit doesn't change what a first-time user's forecast computes.
  const [statePension, setStatePension] = useState<string>("0");
  const [monthlySavings, setMonthlySavings] = useState(250);
  const [monthlySpending, setMonthlySpending] = useState(2000);
  const [employerContributionMonthly, setEmployerContributionMonthly] =
    useState(150);
  const [careerPathIndex, setCareerPathIndex] = useState(1);
  const [data, setData] = useState<{ age: number; income: number }[]>([]);
  const [projectedPot, setProjectedPot] = useState<number | null>(null);
  const [pensionPot, setPensionPot] = useState<number | null>(null);
  // Seeded from the owner's portfolio on mount/owner change so the snapshot
  // card shows a real figure before the user runs a forecast (#7211) --
  // separate from `pensionPot`, which is only ever set from a forecast
  // response and takes priority once populated.
  const [portfolioPensionPot, setPortfolioPensionPot] = useState<
    number | null
  >(null);
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

    const fallbackOwner = owners[0];
    if (!fallbackOwner) return;

    setOwner(fallbackOwner.owner);
    setSelectedOwner(fallbackOwner.owner);
  }, [owners, selectedOwner, setSelectedOwner]);

  // Seed the "Current pension pot" snapshot from the owner's portfolio (the
  // same data the Dashboard already shows) so it reads a real figure on load
  // instead of "Not available" -- see #7211. This never overwrites
  // `pensionPot`, which only comes from an actual forecast response, so it
  // cannot change what a forecast calculates -- it only fills the gap before
  // the first Forecast run.
  useEffect(() => {
    if (!owner) {
      setPortfolioPensionPot(null);
      return;
    }
    let cancelled = false;
    getPortfolio(owner)
      .then((portfolio) => {
        if (cancelled) return;
        const pensionAccounts = portfolio.accounts.filter((account) =>
          isPensionAccountType(account.account_type),
        );
        if (pensionAccounts.length === 0) {
          setPortfolioPensionPot(null);
          return;
        }
        const total = pensionAccounts.reduce(
          (sum, account) => sum + (account.value_estimate_gbp ?? 0),
          0,
        );
        setPortfolioPensionPot(total);
      })
      .catch(() => {
        // Portfolio fetch failing shouldn't break the page -- the snapshot
        // card just falls back to its "run a forecast" copy.
        if (!cancelled) setPortfolioPensionPot(null);
      });
    return () => {
      cancelled = true;
    };
  }, [owner]);

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

  const ownerAccounts = useMemo(() => {
    const ownerSummary = owners.find((o) => o.owner === owner);
    return ownerSummary?.accounts ?? [];
  }, [owners, owner]);

  // Every account type on the owner is still listed here (we deliberately do
  // NOT filter ISAs out, per the issue's own guidance -- filtering would
  // change which accounts are presented as part of the forecast, which is a
  // modelling decision, not a display one, #7211). Each entry carries its
  // display label and whether it's a pension wrapper so the list can be
  // relabelled and visually distinguished instead.
  const ownerAccountDetails = useMemo(
    () =>
      ownerAccounts.map((accountType) => ({
        accountType,
        label: accountTypeLabel(accountType),
        isPension: isPensionAccountType(accountType),
      })),
    [ownerAccounts],
  );

  // The forecast's own response (`pensionPot`) always wins once it exists;
  // until then, fall back to the portfolio-derived figure (#7211).
  const displayedPensionPot = pensionPot ?? portfolioPensionPot;

  const humanizeForecastError = (
    rawMessage: string,
    context: { deathAge: number; retirementAge: number | null; status?: number },
  ): string => {
    const knownDetailMessages: Record<
      string,
      (ctx: typeof context) => string
    > = {
      "death_age must exceed retirement_age": (ctx) =>
        ctx.retirementAge != null
          ? `Death age (${ctx.deathAge}) must be after your retirement age (${ctx.retirementAge}).`
          : `Death age (${ctx.deathAge}) must be after your retirement age.`,
      "missing or invalid dob": () =>
        "We couldn't determine this owner's date of birth. Please check their profile details and try again.",
    };

    const handler = knownDetailMessages[rawMessage.trim()];
    if (handler) return handler(context);

    // Only an unrecognised *client* error is safely described as an input
    // problem. Everything else -- a 5xx, a timeout, a network failure -- is
    // not the user's inputs, and api.ts has already turned those into
    // readable copy ("The backend service is temporarily unavailable...",
    // the timeout message). Telling the user to "check your inputs" when the
    // backend is down sends them to fix something that isn't broken, so pass
    // the message through instead.
    const status = context.status;
    if (status != null && status >= 400 && status < 500) {
      return "We couldn't calculate this forecast. Please check your inputs and try again.";
    }
    return (
      rawMessage.trim() ||
      "We couldn't calculate this forecast. Please try again."
    );
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
      const rawMessage = ex instanceof Error ? ex.message : String(ex);
      const status =
        typeof ex?.status === "number" ? (ex.status as number) : undefined;
      setErr(
        humanizeForecastError(rawMessage, { deathAge, retirementAge, status }),
      );
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
        <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
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
          </div>
          <div className="w-full md:w-auto">
            <label
              htmlFor="pension-owner"
              className="text-xs font-semibold uppercase tracking-wide text-blue-200"
            >
              {t("owner.label")}
            </label>
            <select
              id="pension-owner"
              value={owner}
              onChange={(event) => handleSelectOwner(event.target.value)}
              className="mt-1 w-full min-w-[12rem] rounded-md border border-white/30 bg-slate-900/60 px-3 py-2 text-sm font-medium text-white shadow-sm transition focus:border-white focus:outline-none focus:ring-2 focus:ring-white/60 focus:ring-offset-2 focus:ring-offset-slate-900 disabled:cursor-not-allowed disabled:border-white/10 disabled:text-blue-200/60"
              disabled={owners.length === 0}
            >
              {owners.map((o) => (
                <option key={o.owner} value={o.owner}>
                  {o.full_name?.trim() ? o.full_name : o.owner}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div className="mt-6">
          <p className="text-xs font-semibold uppercase tracking-wide text-blue-200">
            {t("pensionForecast.header.linkedPotsHeading")}
          </p>
          {/* Renamed from "Linked pension pots" and every account type is
              still shown (see ownerAccountDetails above) -- ISAs are not
              pensions, so each chip is labelled with its real account type
              and tagged to show whether it's a pension, rather than being
              filtered out or implied to be one (#7211). */}
          <p className="mt-1 text-xs text-blue-100">
            {t("pensionForecast.header.accountsHelper")}
          </p>
          {ownerAccountDetails.length > 0 ? (
            <ul className="mt-3 flex flex-wrap gap-2">
              {ownerAccountDetails.map(({ accountType, label, isPension }) => (
                <li
                  key={accountType}
                  className="flex items-center gap-1.5 rounded-full bg-white/10 px-3 py-1 text-xs font-medium text-white"
                >
                  <span>{label}</span>
                  <span
                    className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${
                      isPension
                        ? "bg-emerald-400/20 text-emerald-200"
                        : "bg-white/10 text-blue-200"
                    }`}
                  >
                    {isPension
                      ? t("pensionForecast.header.pensionBadge")
                      : t("pensionForecast.header.notPensionBadge")}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-3 text-sm text-blue-100">
              {t("pensionForecast.header.noLinkedPots")}
            </p>
          )}
        </div>
        <dl className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <SnapshotStat
            label={t("pensionForecast.header.pensionPot")}
            value={
              displayedPensionPot != null
                ? currencyFormatter.format(displayedPensionPot)
                : t("pensionForecast.header.notAvailable")
            }
            helper={
              displayedPensionPot != null && pensionPot == null
                ? t("pensionForecast.header.pensionPotFromPortfolio")
                : undefined
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
              // £250/£150 starting values below aren't derived from this
              // owner's actual contributions (not currently available to this
              // page) -- say so explicitly rather than implying they're the
              // owner's real numbers (#7211).
              helper={t("pensionForecast.header.contributionDefaultHelper")}
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
              helper={t("pensionForecast.header.contributionDefaultHelper")}
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
                {/* Relabelled from "Death age" -- blunt phrasing for this
                    audience -- to "Plan until age" (#7211). The underlying
                    field/param name (`deathAge`) is unchanged, so error
                    messages that already reference it (#7134) still work. */}
                <label className="block text-sm font-medium text-slate-700" htmlFor="death-age">
                  {t("pensionForecast.header.deathAgeLabel")}
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
                  aria-describedby="death-age-description"
                />
                <p id="death-age-description" className="text-xs text-slate-500">
                  {t("pensionForecast.header.deathAgeHelper")}
                </p>
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
                  aria-describedby="state-pension-description"
                />
                <p id="state-pension-description" className="text-xs text-slate-500">
                  {t("pensionForecast.header.statePensionHelper")}
                </p>
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
                label={t("pensionForecast.currentAge", {
                  age: Math.round(currentAge),
                })}
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
              <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}>
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
