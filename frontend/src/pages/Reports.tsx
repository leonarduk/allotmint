import { useContext, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { API_BASE, getOwners } from "../api";
import { OwnerSelector } from "../components/OwnerSelector";
import { deleteReportTemplate } from "../api/reports";
import { useReportsCatalog } from "../hooks/useReportsCatalog";
import type { ReportsLocationState } from "./ReportTemplateCreator";
import type {
  OwnerSummary,
  ReportTemplateMetadata,
} from "../types";
import { sanitizeOwners } from "../utils/owners";
import { useDefaultOwner } from "../hooks/useDefaultOwner";
import { RouteContext } from "../contexts/route";
import { completeTrackedChore } from "../choreCompletion";

function buildFieldSummary(template: ReportTemplateMetadata, t: TFunction) {
  const columnMap = new Map<string, string>();
  for (const section of template.sections) {
    for (const column of section.columns) {
      if (!columnMap.has(column.key)) {
        columnMap.set(column.key, column.label);
      }
    }
  }

  const labels = Array.from(columnMap.values());
  if (labels.length === 0) {
    return t("reports.catalog.noFields");
  }

  const preview = labels.slice(0, 4).join(", ");
  const remaining = labels.length - Math.min(labels.length, 4);
  const countKey = labels.length === 1 ? "one" : "other";
  const summary = t(`reports.catalog.fieldsLabel_${countKey}`, {
    count: labels.length,
    fields: preview,
  });

  if (remaining <= 0) {
    return summary;
  }

  const moreKey = remaining === 1 ? "one" : "other";
  const moreLabel = t(`reports.catalog.moreFields_${moreKey}`, {
    count: remaining,
  });
  return `${summary} ${moreLabel}`;
}

function TemplateGroup({
  title,
  templates,
  selectedTemplateId,
  onSelect,
  onDelete,
  deletingId,
  t,
}: {
  title: string;
  templates: ReportTemplateMetadata[];
  selectedTemplateId: string | null;
  onSelect: (templateId: string) => void;
  /** Only passed for custom templates: built-ins stay read-only. */
  onDelete?: (template: ReportTemplateMetadata) => void;
  deletingId?: string | null;
  t: TFunction;
}) {
  if (!templates.length) return null;

  return (
    <div className="space-y-4">
      <h3 className="text-sm font-semibold uppercase tracking-wide text-[var(--surface-muted-color)]">
        {title}
      </h3>
      <ul className="space-y-4">
        {templates.map((template) => {
          const checked = template.template_id === selectedTemplateId;
          const sectionsLabel = template.sections.length
            ? t("reports.catalog.sectionsLabel", {
                sections: template.sections
                  .map((section) => section.title)
                  .join(", "),
              })
            : null;
          const fieldsLabel = buildFieldSummary(template, t);

          return (
            <li key={template.template_id} className="flex items-start gap-2">
              <label
                className={`flex gap-4 rounded-lg border bg-[var(--surface-card-bg)] p-4 text-[var(--surface-card-color)] shadow-sm transition focus-within:ring-2 focus-within:ring-indigo-400/40 ${
                  checked
                    ? "border-indigo-500 ring-2 ring-indigo-400/40"
                    : "border-[var(--surface-card-border)] hover:border-indigo-400"
                } flex-1`}
              >
                <input
                  type="radio"
                  name="report-template"
                  value={template.template_id}
                  checked={checked}
                  onChange={() => onSelect(template.template_id)}
                  className="mt-1 h-4 w-4 text-indigo-600 focus:ring-indigo-500"
                  aria-label={t("reports.catalog.selectLabel", {
                    name: template.name,
                  })}
                />
                <div className="flex flex-col gap-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-lg font-medium">
                      {template.name}
                    </span>
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs font-semibold uppercase tracking-wide ${
                        template.builtin
                          ? "bg-indigo-100 text-indigo-700"
                          : "bg-emerald-100 text-emerald-700"
                      }`}
                    >
                      {t(
                        `reports.catalog.badge.${
                          template.builtin ? "builtin" : "custom"
                        }`,
                      )}
                    </span>
                    {checked ? (
                      <span className="text-xs font-medium text-indigo-500">
                        {t("reports.catalog.selected")}
                      </span>
                    ) : null}
                  </div>
                  {template.description ? (
                    <p className="text-sm text-[var(--surface-muted-color)]">
                      {template.description}
                    </p>
                  ) : null}
                  {sectionsLabel ? (
                    <p className="text-xs uppercase tracking-wide text-[var(--surface-muted-color)]">
                      {sectionsLabel}
                    </p>
                  ) : null}
                  <p className="text-sm text-[var(--surface-muted-color)]">{fieldsLabel}</p>
                </div>
              </label>
              {onDelete && !template.builtin ? (
                <button
                  type="button"
                  onClick={() => onDelete(template)}
                  disabled={deletingId === template.template_id}
                  aria-label={t("reports.catalog.deleteLabel", {
                    name: template.name,
                  })}
                  className="mt-4 rounded border border-red-300 px-3 py-1 text-sm font-medium text-[var(--gain-negative)] hover:bg-red-500/10 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {deletingId === template.template_id
                    ? t("reports.builder.deleting")
                    : t("reports.catalog.delete")}
                </button>
              ) : null}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export default function Reports() {
  const { t } = useTranslation();
  const [owners, setOwners] = useState<OwnerSummary[]>([]);
  const [ownersLoaded, setOwnersLoaded] = useState(false);
  // Read optionally: useRoute() throws outside a RouteProvider. A picker
  // choice updates the app-level owner (as on Strategy), so a later owner
  // change elsewhere wins too; local state is only the provider-less fallback.
  const route = useContext(RouteContext);
  const [localOwner, setLocalOwner] = useState("");
  const setOwner = route ? route.setSelectedOwner : setLocalOwner;
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  // A template just saved on /reports/new arrives as router state: confirm it
  // and select it so its downloads are one click away (#10914).
  const location = useLocation();
  const navigate = useNavigate();
  // Read once, then dropped from history below so back/forward to /reports
  // doesn't repeat the "saved" notice.
  const [createdTemplate] = useState(
    () => (location.state as ReportsLocationState | null)?.createdTemplate,
  );
  const hasCreatedState = Boolean(
    (location.state as ReportsLocationState | null)?.createdTemplate,
  );
  useEffect(() => {
    if (hasCreatedState) {
      navigate(`${location.pathname}${location.search}`, {
        replace: true,
        state: null,
      });
    }
  }, [hasCreatedState, location.pathname, location.search, navigate]);
  const [explicitTemplateId, setExplicitTemplateId] = useState<string | null>(
    createdTemplate?.template_id ?? null,
  );
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deletedName, setDeletedName] = useState<string | null>(null);

  const { templates, builtin, custom, loading, error, refetch } =
    useReportsCatalog();

  const handleDelete = async (template: ReportTemplateMetadata) => {
    if (
      !window.confirm(
        t("reports.catalog.deleteConfirm", { name: template.name }),
      )
    ) {
      return;
    }
    setDeleteError(null);
    setDeletedName(null);
    setDeletingId(template.template_id);
    try {
      await deleteReportTemplate(template.template_id);
      if (explicitTemplateId === template.template_id) {
        setExplicitTemplateId(null);
      }
      setDeletedName(template.name);
      refetch();
    } catch (err) {
      setDeleteError(
        err instanceof Error && err.message
          ? err.message
          : t("reports.builder.deleteError"),
      );
    } finally {
      setDeletingId(null);
    }
  };

  useEffect(() => {
    getOwners()
      .then((os) => setOwners(sanitizeOwners(os)))
      .catch(() => setOwners([]))
      .finally(() => setOwnersLoaded(true));
  }, []);

  // The picked/route owner wins, then the signed-in user's owner, then
  // owners[0] (#10753).
  const owner = useDefaultOwner(
    owners,
    route ? route.selectedOwner : localOwner,
  );

  const selectedTemplateId = useMemo(() => {
    if (explicitTemplateId) return explicitTemplateId;
    return (
      templates.find((template) => template.builtin)?.template_id ??
      templates[0]?.template_id ??
      null
    );
  }, [explicitTemplateId, templates]);

  const selectedTemplate = useMemo(
    () =>
      templates.find((template) => template.template_id === selectedTemplateId) ??
      null,
    [selectedTemplateId, templates],
  );

  const buildDownloadLink = (format: "csv" | "pdf") => {
    if (!owner || !selectedTemplateId) return null;
    const url = `${API_BASE}/reports/${owner}/${selectedTemplateId}`;
    const params = new URLSearchParams();
    if (start) params.set("start", start);
    if (end) params.set("end", end);
    params.set("format", format);
    return `${url}?${params.toString()}`;
  };

  const csvLink = buildDownloadLink("csv");
  const pdfLink = buildDownloadLink("pdf");

  return (
    <div className="container mx-auto max-w-5xl p-4">
      <h1 className="mb-6 text-2xl md:text-4xl">{t("reports.title")}</h1>
      {ownersLoaded && owners.length === 0 ? (
        <p className="text-sm text-[var(--surface-muted-color)]">{t("reports.noOwners")}</p>
      ) : (
        <OwnerSelector owners={owners} selected={owner} onSelect={setOwner} />
      )}
      <div className="my-6 flex flex-col gap-3 md:flex-row md:items-center">
        <label className="mr-2 text-sm font-medium">
          {t("query.start")}: {" "}
          <input
            type="date"
            value={start}
            onChange={(event) => setStart(event.target.value)}
            className="rounded border border-[var(--input-border)] bg-[var(--input-bg)] px-2 py-1 text-[var(--input-text)]"
          />
        </label>
        <label className="text-sm font-medium">
          {t("query.end")}: {" "}
          <input
            type="date"
            value={end}
            onChange={(event) => setEnd(event.target.value)}
            className="rounded border border-[var(--input-border)] bg-[var(--input-bg)] px-2 py-1 text-[var(--input-text)]"
          />
        </label>
      </div>

      <section className="mt-8 space-y-4">
        <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
          <div>
            <h2 className="text-xl font-semibold">
              {t("reports.templatesTitle")}
            </h2>
            <p className="text-sm text-[var(--surface-muted-color)]">
              {t("reports.templatesDescription")}
            </p>
          </div>
          <Link
            to="/reports/new"
            className="inline-flex items-center self-start rounded bg-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-indigo-500 md:self-auto"
          >
            {t("reports.catalog.create")}
          </Link>
        </div>
        {createdTemplate && !deletedName ? (
          <p role="status" className="text-sm text-[var(--gain-positive)]">
            {t("reports.catalog.created", { name: createdTemplate.name })}
          </p>
        ) : null}
        {deletedName ? (
          <p role="status" className="text-sm text-[var(--gain-positive)]">
            {t("reports.catalog.deleted", { name: deletedName })}
          </p>
        ) : null}
        {deleteError ? (
          <p role="alert" className="text-sm text-[var(--gain-negative)]">
            {deleteError}
          </p>
        ) : null}
        <div className="space-y-8">
          {loading ? (
            <p className="text-sm text-[var(--surface-muted-color)]">
              {t("reports.templatesLoading")}
            </p>
          ) : error ? (
            <p className="text-sm text-[var(--gain-negative)]">
              {t("reports.templatesError")}
            </p>
          ) : templates.length === 0 ? (
            <p className="text-sm text-[var(--surface-muted-color)]">
              {t("reports.templatesEmpty")}
            </p>
          ) : (
            <>
              <TemplateGroup
                title={t("reports.catalog.groups.builtin")}
                templates={builtin}
                selectedTemplateId={selectedTemplateId}
                onSelect={setExplicitTemplateId}
                t={t}
              />
              <TemplateGroup
                title={t("reports.catalog.groups.custom")}
                templates={custom}
                selectedTemplateId={selectedTemplateId}
                onSelect={setExplicitTemplateId}
                onDelete={handleDelete}
                deletingId={deletingId}
                t={t}
              />
            </>
          )}
        </div>
      </section>

      <section className="mt-10 space-y-3">
        <h2 className="text-xl font-semibold">
          {t("reports.downloadsTitle")}
        </h2>
        <p className="text-sm text-[var(--surface-muted-color)]">
          {t("reports.downloadsDescription")}
        </p>
        {owner && selectedTemplate ? (
          <div className="flex flex-wrap items-center gap-4">
            <a
              href={csvLink ?? undefined}
              onClick={() => completeTrackedChore("run_a_report")}
              className="inline-flex items-center rounded bg-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-indigo-500"
            >
              {t("reports.csv")}
            </a>
            <a
              href={pdfLink ?? undefined}
              onClick={() => completeTrackedChore("run_a_report")}
              className="inline-flex items-center rounded border border-indigo-500 px-4 py-2 text-sm font-semibold text-indigo-500 transition hover:bg-indigo-500/10"
            >
              {t("reports.pdf")}
            </a>
            <span className="text-xs text-[var(--surface-muted-color)]">
              {t("reports.catalog.selectedTemplate", {
                name: selectedTemplate.name,
              })}
            </span>
          </div>
        ) : (
          <p className="text-sm text-[var(--surface-muted-color)]">
            {t("reports.downloadsDisabled")}
          </p>
        )}
      </section>
    </div>
  );
}
