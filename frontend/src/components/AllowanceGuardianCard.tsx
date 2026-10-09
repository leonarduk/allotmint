import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  getAllowanceGuardian,
  type AllowanceGuardianReport,
  type GuardianIsaAllowance,
  type GuardianPensionAllowance,
  type GuardianUnavailable,
} from "../api";
import { money } from "../lib/money";

/** Pence (`*_minor`) to a £ string. */
const formatMinor = (minor: number | null | undefined): string => money(minor == null ? null : minor / 100);

const ALERT_CLASSES: Record<string, string> = {
  critical: "border-red-500 text-red-700 dark:text-red-300",
  warning: "border-amber-500 text-amber-700 dark:text-amber-300",
  info: "border-sky-500 text-sky-700 dark:text-sky-300",
};

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4 py-0.5">
      <dt>{label}</dt>
      <dd className="text-right font-medium">{value}</dd>
    </div>
  );
}

function PensionSection({ pension }: { pension: GuardianPensionAllowance | GuardianUnavailable }) {
  const { t } = useTranslation();
  if (!pension.available) return <p className="text-sm">{t("allowanceGuardian.unavailable")}</p>;
  const available = pension.current_year_remaining_minor + pension.carry_forward_available_minor;
  return (
    <dl className="text-sm">
      <Row label={t("allowanceGuardian.annualAllowance")} value={formatMinor(pension.annual_allowance_minor)} />
      <Row label={t("allowanceGuardian.usedToDate")} value={formatMinor(pension.used_to_date_minor)} />
      <Row label={t("allowanceGuardian.carryForward")} value={formatMinor(pension.carry_forward_available_minor)} />
      <Row label={t("allowanceGuardian.availableTotal")} value={formatMinor(available)} />
      <Row label={t("allowanceGuardian.scheduledRemaining")} value={formatMinor(pension.scheduled_remaining_minor)} />
      <Row label={t("allowanceGuardian.projectedTotal")} value={formatMinor(pension.projected_total_minor)} />
      <Row
        label={t("allowanceGuardian.carryForwardFirstNeeded")}
        value={pension.carry_forward_first_needed?.month ?? t("allowanceGuardian.none")}
      />
      <Row
        label={t("allowanceGuardian.projectedBreach")}
        value={pension.projected_breach?.month ?? t("allowanceGuardian.none")}
      />
    </dl>
  );
}

function IsaSection({ isa }: { isa: GuardianIsaAllowance | GuardianUnavailable }) {
  const { t } = useTranslation();
  if (!isa.available) return <p className="text-sm">{t("allowanceGuardian.unavailable")}</p>;
  return (
    <dl className="text-sm">
      <Row label={t("allowanceGuardian.isaSubscribed")} value={formatMinor(isa.subscribed_minor)} />
      <Row label={t("allowanceGuardian.isaLimit")} value={formatMinor(isa.limit_minor)} />
      <Row label={t("allowanceGuardian.scheduledRemaining")} value={formatMinor(isa.scheduled_remaining_minor)} />
      <Row label={t("allowanceGuardian.projectedTotal")} value={formatMinor(isa.projected_total_minor)} />
      <Row
        label={t("allowanceGuardian.isaDeadline")}
        value={t("allowanceGuardian.daysTo", { days: isa.days_to_deadline, date: isa.deadline })}
      />
    </dl>
  );
}

function ContributionsTable({ report }: { report: AllowanceGuardianReport }) {
  const { t } = useTranslation();
  const rows = report.contributions.results;
  if (report.schedule_count === 0) return <p className="text-sm">{t("allowanceGuardian.noSchedule")}</p>;
  if (!rows.length) return <p className="text-sm">{t("allowanceGuardian.noneExpected")}</p>;
  return (
    <table className="min-w-full border-collapse text-sm">
      <thead>
        <tr>
          <th className="border p-1 text-left">{t("allowanceGuardian.expectedDate")}</th>
          <th className="border p-1 text-left">{t("allowanceTracker.account")}</th>
          <th className="border p-1 text-right">{t("allowanceGuardian.expected")}</th>
          <th className="border p-1 text-right">{t("allowanceGuardian.received")}</th>
          <th className="border p-1 text-left">{t("allowanceGuardian.statusHeading")}</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={`${row.account}-${row.source}-${row.expected_date}-${row.label ?? ""}`}>
            <td className="border p-1">{row.expected_date}</td>
            <td className="border p-1">{row.label ?? row.account}</td>
            <td className="border p-1 text-right">{formatMinor(row.expected_amount_minor)}</td>
            <td className="border p-1 text-right">{formatMinor(row.received_amount_minor)}</td>
            <td className="border p-1">{t(`allowanceGuardian.status.${row.status}`)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function GuardianBody({ report }: { report: AllowanceGuardianReport }) {
  const { t } = useTranslation();
  return (
    <>
      {report.alerts.length > 0 && (
        <ul className="mb-3 space-y-1" aria-label={t("allowanceGuardian.alerts")}>
          {report.alerts.map((alert) => (
            <li key={alert.code} className={`border-l-4 pl-2 text-sm ${ALERT_CLASSES[alert.level] ?? ""}`}>
              {alert.message}
            </li>
          ))}
        </ul>
      )}
      <div className="grid gap-4 md:grid-cols-2">
        <section>
          <h3 className="mb-1 font-semibold">{t("allowanceGuardian.pensionHeading")}</h3>
          <PensionSection pension={report.pension_allowance} />
        </section>
        <section>
          <h3 className="mb-1 font-semibold">{t("allowanceGuardian.isaHeading")}</h3>
          <IsaSection isa={report.isa_allowance} />
        </section>
      </div>
      <section className="mt-4">
        <h3 className="mb-1 font-semibold">{t("allowanceGuardian.contributionsHeading")}</h3>
        <ContributionsTable report={report} />
      </section>
    </>
  );
}

/**
 * Contribution & allowance guardian (#10479): expected-vs-actual contributions and the
 * pension/ISA allowance projected to 5 April. Facts only; the not-modelled list and
 * adviser note are always shown, whether or not the report loaded.
 */
export default function AllowanceGuardianCard({ owner }: { owner: string }) {
  const { t } = useTranslation();
  const [report, setReport] = useState<AllowanceGuardianReport | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let active = true;
    const load = async () => {
      setReport(null);
      setError(false);
      try {
        const res = await getAllowanceGuardian(owner);
        if (active) setReport(res);
      } catch {
        if (active) setError(true);
      }
    };
    void load();
    return () => {
      active = false;
    };
  }, [owner]);

  return (
    <section className="mt-6 rounded border border-gray-300 p-4" aria-labelledby="allowance-guardian-title">
      <h2 id="allowance-guardian-title" className="mb-1 text-xl">
        {t("allowanceGuardian.title")}
      </h2>
      {report && (
        <p className="mb-3 text-xs opacity-75">{t("allowanceGuardian.asOf", { date: report.as_of, year: report.tax_year })}</p>
      )}
      {error && <p className="text-red-500">{t("allowanceGuardian.loadFailed")}</p>}
      {!report && !error && <p role="status">{t("app.loading")}</p>}
      {report && <GuardianBody report={report} />}
      <section className="mt-4 text-xs">
        <h3 className="font-semibold">{t("allowanceGuardian.notModelledHeading")}</h3>
        <ul className="list-disc pl-5">
          {(report?.not_modelled ?? [t("allowanceGuardian.notModelledFallback")]).map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
        <p className="mt-2">{report?.adviser_note ?? t("allowanceGuardian.adviserNoteFallback")}</p>
      </section>
    </section>
  );
}
