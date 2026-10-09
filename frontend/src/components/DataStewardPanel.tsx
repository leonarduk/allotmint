import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import {
  fixDataQualityIssue,
  getBotRun,
  getDataStewardLatest,
  runBotNow,
  type DataStewardItem,
  type DataStewardReport,
  type DataStewardVerdict,
} from "../api";
import { entityLabel, researchSymbol } from "../lib/dataQualityEntity";
import EmptyState from "./EmptyState";
import { Modal } from "./Modal";
import { ResearchLink } from "./ResearchLink";

const VERDICT_GROUPS: readonly DataStewardVerdict[] = ["fix_available", "needs_human", "not_a_problem", "error"];
const STEWARD_BOT_ID = "data-steward";
const RUN_POLL_MS = 3000;

function formatGbp(value: number | null): string {
  if (value == null) return "—";
  return `£${value.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

function errorMessage(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

function Evidence({ item }: { item: DataStewardItem }) {
  const { t } = useTranslation();
  if (item.evidence.length === 0) return null;
  return (
    <details className="mt-2">
      <summary className="cursor-pointer text-sm">
        {t("dataQuality.admin.steward.evidence", { count: item.evidence.length })}
      </summary>
      <ol className="ml-4 list-decimal text-xs">
        {item.evidence.map((ev, index) => (
          <li key={index} className="mb-2">
            <code>
              {ev.tool}({JSON.stringify(ev.arguments)})
            </code>
            {ev.is_error && <span className="ml-2 text-red-700">{t("dataQuality.admin.steward.toolError")}</span>}
            <pre className="max-h-48 overflow-auto rounded bg-gray-100 p-2 text-slate-900">
              {ev.truncated ? `${ev.result}\n…` : ev.result}
            </pre>
          </li>
        ))}
      </ol>
    </details>
  );
}

function Findings({ item }: { item: DataStewardItem }) {
  const { t } = useTranslation();
  return (
    <>
      {item.root_cause && (
        <p className="text-sm">
          {t("dataQuality.admin.steward.rootCause")}: <code>{item.root_cause}</code>
          {item.confidence != null &&
            ` · ${t("dataQuality.admin.steward.confidence", { pct: Math.round(item.confidence * 100) })}`}
        </p>
      )}
      {item.summary && <p className="text-sm">{item.summary}</p>}
      {item.error && <p className="text-sm text-red-700">{item.error}</p>}
      {item.allowlist_reason && (
        <p className="text-sm">
          {t("dataQuality.admin.steward.allowlistReason")}: {item.allowlist_reason}
        </p>
      )}
      {item.unclear && item.unclear.length > 0 && (
        <p className="text-sm">
          {t("dataQuality.admin.steward.unclear")}: {item.unclear.join("; ")}
        </p>
      )}
    </>
  );
}

function ItemCard({
  item,
  onApply,
  applying,
  applied,
}: {
  item: DataStewardItem;
  onApply: (item: DataStewardItem) => void;
  applying: boolean;
  applied: boolean;
}) {
  const { t } = useTranslation();
  const label = entityLabel(item.entity);
  return (
    <li className="mb-3 rounded border border-slate-300 p-3" data-testid={`steward-item-${item.issue_id}`}>
      <div className="flex flex-wrap items-baseline gap-2">
        <strong>
          <ResearchLink symbol={researchSymbol(item.entity)}>{label}</ResearchLink>
        </strong>
        <span className="text-xs opacity-70">
          {item.issue_type} · {item.severity}
        </span>
        <span className="text-sm">
          {t("dataQuality.admin.steward.exposure", {
            value: formatGbp(item.exposure_gbp),
            pct: item.exposure_pct == null ? "—" : `${item.exposure_pct}%`,
          })}
        </span>
      </div>
      <Findings item={item} />
      {item.proposed_fix && (
        <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
          <span>
            {t("dataQuality.admin.steward.proposedFix")}: {item.proposed_fix.description ?? item.proposed_fix.path}
          </span>
          {applied ? (
            <span className="text-green-700">{t("dataQuality.admin.steward.applied")}</span>
          ) : (
            <button
              type="button"
              onClick={() => onApply(item)}
              disabled={applying}
              aria-label={t("dataQuality.admin.steward.applyFor", { entity: label })}
            >
              {applying ? t("dataQuality.admin.issues.actions.fixing") : t("dataQuality.admin.issues.actions.apply")}
            </button>
          )}
        </div>
      )}
      <Evidence item={item} />
    </li>
  );
}

function RunSummary({ report }: { report: DataStewardReport }) {
  const { t } = useTranslation();
  const cost = report.totals.cost_usd == null ? "—" : `$${report.totals.cost_usd.toFixed(4)}`;
  return (
    <>
      <p className="mb-2 text-sm opacity-80">
        {t("dataQuality.admin.steward.runSummary", {
          when: new Date(report.started_at).toLocaleString(),
          status: report.status,
          model: `${report.provider}/${report.model}`,
          investigated: report.issues_investigated,
          held: report.issues_held,
          found: report.issues_found,
          tokens: report.totals.input_tokens + report.totals.output_tokens,
          cost,
        })}
      </p>
      {report.errors.length > 0 && (
        <ul aria-label={t("dataQuality.admin.steward.runErrors")} className="mb-2 text-sm text-red-700">
          {report.errors.map((err, index) => (
            <li key={index}>
              {err.stage}: {err.error}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

function VerdictGroups({
  report,
  onApply,
  applyingId,
  appliedIds,
}: {
  report: DataStewardReport;
  onApply: (item: DataStewardItem) => void;
  applyingId: string | null;
  appliedIds: ReadonlySet<string>;
}) {
  const { t } = useTranslation();
  if (report.items.length === 0) return <p className="text-sm">{t("dataQuality.admin.steward.noItems")}</p>;
  return (
    <>
      {VERDICT_GROUPS.map((verdict) => {
        const items = report.items.filter((item) => item.verdict === verdict);
        if (items.length === 0) return null;
        const title = t(`dataQuality.admin.steward.groups.${verdict}`);
        return (
          <section key={verdict} className="mb-4" aria-label={title}>
            <h3 className="mb-2 text-lg">
              {title} ({items.length})
            </h3>
            <ul>
              {items.map((item) => (
                <ItemCard
                  key={item.issue_id}
                  item={item}
                  onApply={onApply}
                  applying={applyingId === item.issue_id}
                  applied={appliedIds.has(item.issue_id)}
                />
              ))}
            </ul>
          </section>
        );
      })}
    </>
  );
}

function ConfirmFix({
  item,
  applying,
  onCancel,
  onConfirm,
}: {
  item: DataStewardItem;
  applying: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const { t } = useTranslation();
  return (
    <Modal onClose={onCancel} labelledBy="dq-steward-confirm-title" className="w-full max-w-md rounded-lg bg-white p-6 text-slate-900">
      <h3 id="dq-steward-confirm-title" className="mb-2 text-lg font-semibold">
        {t("dataQuality.admin.issues.actions.confirmTitle")}
      </h3>
      <p className="mb-2 text-sm">{item.proposed_fix?.description ?? item.description}</p>
      <p className="mb-4 text-xs opacity-70">{t("dataQuality.admin.issues.actions.confirmBody")}</p>
      <div className="flex justify-end gap-2">
        <button
          type="button"
          className="rounded border border-slate-300 bg-white px-4 py-2 text-slate-900 hover:bg-slate-100"
          onClick={onCancel}
        >
          {t("dataQuality.admin.issues.actions.cancel")}
        </button>
        <button
          type="button"
          className="rounded bg-slate-900 px-4 py-2 text-white hover:bg-slate-700 disabled:opacity-50"
          onClick={onConfirm}
          disabled={applying}
        >
          {applying ? t("dataQuality.admin.issues.actions.fixing") : t("dataQuality.admin.issues.actions.apply")}
        </button>
      </div>
    </Modal>
  );
}

/**
 * The data steward's latest triage report (#10471): issues grouped by verdict, with
 * the evidence behind each. "Apply" calls the existing data-quality fix endpoint, so
 * a person always confirms a change; the steward itself never writes data.
 */
export function DataStewardPanel() {
  const { t } = useTranslation();
  const [report, setReport] = useState<DataStewardReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<DataStewardItem | null>(null);
  const [applyingId, setApplyingId] = useState<string | null>(null);
  // Fixes applied since this report was produced: shown as applied, not offered again.
  const [appliedIds, setAppliedIds] = useState<ReadonlySet<string>>(new Set());

  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    getDataStewardLatest()
      .then(setReport)
      .catch((e: unknown) => setError(errorMessage(e)))
      .finally(() => setLoading(false));
    return () => {
      mounted.current = false;
    };
  }, []);

  // Run now goes through the Bots framework (#10477), which records the run and
  // runs it in the background (its own Lambda on AWS); poll until it finishes.
  const runNow = async () => {
    setRunning(true);
    setError(null);
    setMessage(null);
    try {
      let run = await runBotNow(STEWARD_BOT_ID);
      while (run.status === "running" && mounted.current) {
        await new Promise((resolve) => setTimeout(resolve, RUN_POLL_MS));
        run = await getBotRun(STEWARD_BOT_ID, run.id);
      }
      if (!mounted.current) return;
      if (run.status === "failed" || run.status === "skipped") {
        setError(run.error || run.summary || run.status);
      }
      setReport(await getDataStewardLatest());
      setAppliedIds(new Set());
    } catch (e) {
      if (mounted.current) setError(errorMessage(e));
    } finally {
      if (mounted.current) setRunning(false);
    }
  };

  const applyFix = async (item: DataStewardItem) => {
    setApplyingId(item.issue_id);
    setError(null);
    setMessage(null);
    try {
      // The existing endpoint re-checks the issue, backs up the file and audits the change.
      await fixDataQualityIssue(item.issue_id);
      setAppliedIds((prev) => new Set(prev).add(item.issue_id));
      setMessage(t("dataQuality.admin.issues.actions.applied"));
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setApplyingId(null);
      setConfirming(null);
    }
  };

  if (loading) return <div>{t("common.loading")}</div>;

  return (
    <div>
      <h2 className="mb-2 text-xl">{t("dataQuality.admin.steward.title")}</h2>
      <p className="mb-2 text-sm opacity-70">{t("dataQuality.admin.steward.subtitle")}</p>
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <button type="button" onClick={runNow} disabled={running}>
          {running ? t("dataQuality.admin.steward.running") : t("dataQuality.admin.steward.runNow")}
        </button>
        <Link to="/bots" className="text-sm underline">
          {t("dataQuality.admin.steward.botsLink")}
        </Link>
      </div>
      {message && <p role="status" className="mb-2 text-green-700">{message}</p>}
      {error && <p role="alert" className="mb-2 text-red-700">{error}</p>}
      {report ? (
        <>
          <RunSummary report={report} />
          <VerdictGroups report={report} onApply={setConfirming} applyingId={applyingId} appliedIds={appliedIds} />
        </>
      ) : (
        <EmptyState message={t("dataQuality.admin.steward.empty")} actions={[]} />
      )}
      {confirming && (
        <ConfirmFix
          item={confirming}
          applying={applyingId === confirming.issue_id}
          onCancel={() => setConfirming(null)}
          onConfirm={() => applyFix(confirming)}
        />
      )}
    </div>
  );
}
