import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";

import { API_BASE, getOwners } from "../api";
import { OwnerSelector } from "../components/OwnerSelector";
import { useReportsCatalog } from "../hooks/useReportsCatalog";
import type {
  OwnerSummary,
  ReportTemplateMetadata,
} from "../types";
import { sanitizeOwners } from "../utils/owners";

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
  t,
}: {
  title: string;
  templates: ReportTemplateMetadata[];
  selectedTemplateId: string | null;
  onSelect: (templateId: string) => void;
  t: TFunction;
}) {
  if (!templates.length) return null;

  return (
    <div className="space-y-4">
      <h3 className="text-sm font-semibold uppercase tracking-wide text-gray-500">
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
            <li key={template.template_id}>
              <label
                className={`flex gap-4 rounded-lg border p-4 shadow-sm transition focus-within:ring-2 focus-within:ring-indigo-200 ${
                  checked
                    ? "border-indigo-500 ring-2 ring-indigo-200"
                    : "border-gray-200 hover:border-indigo-300"
                }`}
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
                    <span className="text-lg font-medium text-gray-900">
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
                      <span className="text-xs font-medium text-indigo-600">
                        {t("reports.catalog.selected")}
                      </span>
                    ) : null}
                  </div>
                  {template.description ? (
                    <p className="text-sm text-gray-600">
                      {template.description}
                    </p>
                  ) : null}
                  {sectionsLabel ? (
                    <p className="text-xs uppercase tracking-wide text-gray-500">
                      {sectionsLabel}
                    </p>
                  ) : null}
                  <p className="text-sm text-gray-600">{fieldsLabel}</p>
                </div>
              </label>
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
  const [owner, setOwner] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [selectedTemplateId, setSelectedTemplateId] = useState<string | null>(
    null,
  );

  const { templates, builtin, custom, loading, error } = useReportsCatalog();

  useEffect(() => {
    getOwners()
      .then((os) => setOwners(sanitizeOwners(os)))
      .catch(() => setOwners([]))
      .finally(() => setOwnersLoaded(true));
  }, []);

  useEffect(() => {
    if (templates.length === 0 || selectedTemplateId) return;
    const preferred =
      templates.find((template) => template.builtin) ?? templates[0];
    setSelectedTemplateId(preferred.template_id);
  }, [templates, selectedTemplateId]);

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
        <p className="text-sm text-gray-600">{t("reports.noOwners")}</p>
      ) : (
        <OwnerSelector owners={owners} selected={owner} onSelect={setOwner} />
      )}
      <div className="my-6 flex flex-col gap-3 md:flex-row md:items-center">
        <label className="mr-2 text-sm font-medium text-gray-700">
          {t("query.start")}: {" "}
          <input
            type="date"
            value={start}
            onChange={(event) => setStart(event.target.value)}
            className="rounded border border-gray-300 px-2 py-1"
          />
        </label>
        <label className="text-sm font-medium text-gray-700">
          {t("query.end")}: {" "}
          <input
            type="date"
            value={end}
            onChange={(event) => setEnd(event.target.value)}
            className="rounded border border-gray-300 px-2 py-1"
          />
        </label>
      </div>

      <section className="mt-8 space-y-4">
        <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
          <div>
            <h2 className="text-xl font-semibold">
              {t("reports.templatesTitle")}
            </h2>
            <p className="text-sm text-gray-600">
              {t("reports.templatesDescription")}
            </p>
          </div>
        </div>
        <div className="space-y-8">
          {loading ? (
            <p className="text-sm text-gray-600">
              {t("reports.templatesLoading")}
            </p>
          ) : error ? (
            <p className="text-sm text-red-600">
              {t("reports.templatesError")}
            </p>
          ) : templates.length === 0 ? (
            <p className="text-sm text-gray-600">
              {t("reports.templatesEmpty")}
            </p>
          ) : (
            <>
              <TemplateGroup
                title={t("reports.catalog.groups.builtin")}
                templates={builtin}
                selectedTemplateId={selectedTemplateId}
                onSelect={setSelectedTemplateId}
                t={t}
              />
              <TemplateGroup
                title={t("reports.catalog.groups.custom")}
                templates={custom}
                selectedTemplateId={selectedTemplateId}
                onSelect={setSelectedTemplateId}
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
        <p className="text-sm text-gray-600">
          {t("reports.downloadsDescription")}
        </p>
        {owner && selectedTemplate ? (
          <div className="flex flex-wrap items-center gap-4">
            <a
              href={csvLink ?? undefined}
              className="inline-flex items-center rounded bg-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-indigo-500"
            >
              {t("reports.csv")}
            </a>
            <a
              href={pdfLink ?? undefined}
              className="inline-flex items-center rounded border border-indigo-600 px-4 py-2 text-sm font-semibold text-indigo-600 transition hover:bg-indigo-50"
            >
              {t("reports.pdf")}
            </a>
            <span className="text-xs text-gray-500">
              {t("reports.catalog.selectedTemplate", {
                name: selectedTemplate.name,
              })}
            </span>
          </div>
        ) : (
          <p className="text-sm text-gray-500">
            {t("reports.downloadsDisabled")}
          </p>
        )}
      </section>
    </div>
  );
}
