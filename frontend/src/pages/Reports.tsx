import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useMatch, useNavigate } from "react-router-dom";

import { API_BASE, getOwners } from "../api";
import {
  createReportTemplate,
  deleteReportTemplate,
  getReportTemplate,
  listReportTemplates,
  updateReportTemplate,
} from "../api/reports";
import { OwnerSelector } from "../components/OwnerSelector";
import { ReportBuilder } from "../components/ReportBuilder";
import type { OwnerSummary, ReportTemplate, ReportTemplateInput } from "../types";
import { sanitizeOwners } from "../utils/owners";

export default function Reports() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [owners, setOwners] = useState<OwnerSummary[]>([]);
  const [ownersLoaded, setOwnersLoaded] = useState(false);
  const [owner, setOwner] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");

  const [templates, setTemplates] = useState<ReportTemplate[]>([]);
  const [templatesLoading, setTemplatesLoading] = useState(true);
  const [templatesError, setTemplatesError] = useState<string | null>(null);

  const [fetchedTemplate, setFetchedTemplate] = useState<ReportTemplate | null>(null);
  const [templateLoading, setTemplateLoading] = useState(false);
  const [templateError, setTemplateError] = useState<string | null>(null);

  const newMatch = useMatch("/reports/new");
  const editMatch = useMatch("/reports/:templateId/edit");
  const editingId = editMatch?.params?.templateId ?? null;
  const builderOpen = Boolean(newMatch || editMatch);

  useEffect(() => {
    getOwners()
      .then((os) => setOwners(sanitizeOwners(os)))
      .catch(() => setOwners([]))
      .finally(() => setOwnersLoaded(true));
  }, []);

  useEffect(() => {
    let cancelled = false;
    setTemplatesLoading(true);
    setTemplatesError(null);
    listReportTemplates()
      .then((data) => {
        if (cancelled) return;
        setTemplates(data);
      })
      .catch((error) => {
        if (cancelled) return;
        console.error("Failed to load report templates", error);
        setTemplatesError(t("reports.templatesError"));
      })
      .finally(() => {
        if (cancelled) return;
        setTemplatesLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [t]);

  useEffect(() => {
    if (!editingId) {
      setFetchedTemplate(null);
      setTemplateError(null);
      setTemplateLoading(false);
      return;
    }
    const existing = templates.find((tpl) => tpl.id === editingId);
    if (existing) {
      setFetchedTemplate(null);
      setTemplateError(null);
      setTemplateLoading(false);
      return;
    }
    let cancelled = false;
    setTemplateLoading(true);
    setTemplateError(null);
    getReportTemplate(editingId)
      .then((template) => {
        if (cancelled) return;
        setFetchedTemplate(template);
      })
      .catch((error) => {
        if (cancelled) return;
        console.error("Failed to fetch template", error);
        setTemplateError(t("reports.builder.loadError"));
      })
      .finally(() => {
        if (cancelled) return;
        setTemplateLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [editingId, templates, t]);

  const baseUrl = owner ? `${API_BASE}/reports/${owner}` : null;
  const params = new URLSearchParams();
  if (start) params.set("start", start);
  if (end) params.set("end", end);
  const query = params.toString();

  const editingTemplate = useMemo(() => {
    if (!editingId) return null;
    return templates.find((tpl) => tpl.id === editingId) ?? fetchedTemplate;
  }, [editingId, templates, fetchedTemplate]);

  const handleCloseBuilder = () => {
    navigate("/reports", { replace: true });
  };

  const handleCreateTemplate = async (input: ReportTemplateInput) => {
    const optimisticId = `temp-${Date.now()}`;
    const optimisticTemplate: ReportTemplate = {
      id: optimisticId,
      name: input.name,
      description: input.description,
      metrics: input.metrics,
      columns: input.columns,
      filters: input.filters,
      optimistic: true,
    };
    setTemplates((prev) => [...prev, optimisticTemplate]);
    try {
      const saved = await createReportTemplate(input);
      setTemplates((prev) =>
        prev.map((tpl) => (tpl.id === optimisticId ? saved : tpl)),
      );
    } catch (error) {
      setTemplates((prev) => prev.filter((tpl) => tpl.id !== optimisticId));
      throw error;
    }
  };

  const handleUpdateTemplate = async (id: string, input: ReportTemplateInput) => {
    const previous = templates.find((tpl) => tpl.id === id);
    setTemplates((prev) =>
      prev.map((tpl) =>
        tpl.id === id
          ? { ...tpl, ...input, filters: input.filters, optimistic: true }
          : tpl,
      ),
    );
    try {
      const saved = await updateReportTemplate(id, input);
      setTemplates((prev) => prev.map((tpl) => (tpl.id === id ? saved : tpl)));
    } catch (error) {
      if (previous) {
        setTemplates((prev) => prev.map((tpl) => (tpl.id === id ? previous : tpl)));
      }
      throw error;
    }
  };

  const handleDeleteTemplate = async (id: string) => {
    let snapshot: ReportTemplate[] = [];
    setTemplates((prev) => {
      snapshot = prev;
      return prev.filter((tpl) => tpl.id !== id);
    });
    try {
      await deleteReportTemplate(id);
    } catch (error) {
      setTemplates(snapshot);
      throw error;
    }
  };

  const builderOverlay = (() => {
    if (!builderOpen) return null;
    if (editingId) {
      if (templateLoading) {
        return (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
            <div className="rounded-lg bg-white p-6 shadow-xl">
              <p>{t("reports.builder.loading")}</p>
              <div className="mt-4 flex justify-end">
                <button
                  type="button"
                  onClick={handleCloseBuilder}
                  className="rounded border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100"
                >
                  {t("common.close", "Close")}
                </button>
              </div>
            </div>
          </div>
        );
      }
      if (!editingTemplate) {
        return (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
            <div className="rounded-lg bg-white p-6 shadow-xl">
              <p className="text-sm text-red-600">{templateError ?? t("reports.builder.missing")}</p>
              <div className="mt-4 flex justify-end">
                <button
                  type="button"
                  onClick={handleCloseBuilder}
                  className="rounded border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100"
                >
                  {t("common.close", "Close")}
                </button>
              </div>
            </div>
          </div>
        );
      }
    }
    return (
      <ReportBuilder
        template={editingTemplate ?? undefined}
        onCreate={handleCreateTemplate}
        onUpdate={handleUpdateTemplate}
        onDelete={handleDeleteTemplate}
        onCancel={handleCloseBuilder}
      />
    );
  })();

  const templatesSummary = (template: ReportTemplate) => {
    const metricsLabel = t("reports.templatesCount.metrics", { count: template.metrics.length });
    const columnsLabel = t("reports.templatesCount.columns", { count: template.columns.length });
    const filtersLabel = t("reports.templatesCount.filters", { count: template.filters.length });
    return `${metricsLabel} • ${columnsLabel} • ${filtersLabel}`;
  };

  return (
    <div className="container mx-auto max-w-4xl p-4">
      <h1 className="mb-4 text-2xl md:text-4xl">{t("reports.title")}</h1>
      {ownersLoaded && owners.length === 0 ? (
        <p>{t("reports.noOwners")}</p>
      ) : (
        <OwnerSelector owners={owners} selected={owner} onSelect={setOwner} />
      )}
      <div className="my-4 flex flex-col gap-2 md:flex-row md:items-center">
        <label className="mr-2">
          {t("query.start")}:{" "}
          <input type="date" value={start} onChange={(e) => setStart(e.target.value)} />
        </label>
        <label>
          {t("query.end")}:{" "}
          <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
        </label>
      </div>
      {baseUrl && (
        <p>
          <a href={`${baseUrl}?${query}&format=csv`}>{t("reports.csv")}</a>
          {" | "}
          <a href={`${baseUrl}?${query}&format=pdf`}>{t("reports.pdf")}</a>
        </p>
      )}

      <section className="mt-10">
        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div>
            <h2 className="text-xl font-semibold">{t("reports.templatesTitle")}</h2>
            <p className="text-sm text-gray-600">{t("reports.templatesDescription")}</p>
          </div>
          <button
            type="button"
            onClick={() => navigate("/reports/new")}
            className="self-start rounded bg-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-indigo-500"
          >
            {t("reports.createTemplateButton")}
          </button>
        </div>
        <div className="mt-4">
          {templatesLoading ? (
            <p>{t("reports.templatesLoading")}</p>
          ) : templatesError ? (
            <p className="text-sm text-red-600">{templatesError}</p>
          ) : templates.length === 0 ? (
            <p className="text-sm text-gray-600">{t("reports.templatesEmpty")}</p>
          ) : (
            <ul className="space-y-4">
              {templates.map((template) => (
                <li
                  key={template.id}
                  className="rounded border border-gray-200 p-4 shadow-sm transition hover:border-indigo-300"
                >
                  <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="text-lg font-medium">{template.name}</h3>
                        {template.optimistic && (
                          <span className="text-xs text-gray-500">{t("reports.templatesSaving")}</span>
                        )}
                      </div>
                      {template.description && (
                        <p className="text-sm text-gray-600">{template.description}</p>
                      )}
                      <p className="mt-2 text-xs uppercase tracking-wide text-gray-500">
                        {templatesSummary(template)}
                      </p>
                    </div>
                    <div className="flex gap-2">
                      <button
                        type="button"
                        onClick={() => navigate(`/reports/${template.id}/edit`)}
                        className="rounded border border-gray-300 px-3 py-1 text-sm font-medium text-gray-700 hover:bg-gray-100"
                      >
                        {t("reports.editTemplate")}
                      </button>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>
      {builderOverlay}
    </div>
  );
}
