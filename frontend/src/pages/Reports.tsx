import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { API_BASE, getOwners } from "../api";
import type { OwnerSummary } from "../types";
import { OwnerSelector } from "../components/OwnerSelector";
import { sanitizeOwners } from "../utils/owners";
import { useReportsCatalog } from "../hooks/useReportsCatalog";

const fieldList = (fields: string[] | undefined, label: string) => {
  if (!fields || fields.length === 0) return null;
  return (
    <div className="mt-2">
      <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">
        {label}
      </div>
      <ul className="mt-1 list-disc list-inside text-sm text-slate-600">
        {fields.map((field) => (
          <li key={field}>{field}</li>
        ))}
      </ul>
    </div>
  );
};

export default function Reports() {
  const { t } = useTranslation();
  const [owners, setOwners] = useState<OwnerSummary[]>([]);
  const [ownersLoaded, setOwnersLoaded] = useState(false);
  const [owner, setOwner] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const { builtIn, custom, loading: catalogLoading, error: catalogError } =
    useReportsCatalog();
  const [selectedTemplateId, setSelectedTemplateId] = useState("");

  const filteredCustomTemplates = useMemo(
    () => custom.filter((template) => template.owner === owner),
    [custom, owner],
  );

  const availableTemplates = useMemo(
    () => [...builtIn, ...filteredCustomTemplates],
    [builtIn, filteredCustomTemplates],
  );

  useEffect(() => {
    getOwners()
      .then((os) => setOwners(sanitizeOwners(os)))
      .catch(() => setOwners([]))
      .finally(() => setOwnersLoaded(true));
  }, []);

  useEffect(() => {
    if (!selectedTemplateId && availableTemplates.length > 0) {
      setSelectedTemplateId(availableTemplates[0].id);
    }
  }, [selectedTemplateId, availableTemplates]);

  useEffect(() => {
    if (selectedTemplateId && !availableTemplates.some((tpl) => tpl.id === selectedTemplateId)) {
      setSelectedTemplateId(availableTemplates[0]?.id ?? "");
    }
  }, [availableTemplates, selectedTemplateId]);

  const selectedTemplate = useMemo(
    () => availableTemplates.find((template) => template.id === selectedTemplateId) ?? null,
    [availableTemplates, selectedTemplateId],
  );

  const baseUrl = owner ? `${API_BASE}/reports/${owner}` : null;
  const canDownload = Boolean(baseUrl && selectedTemplate);

  const createDownloadHref = (format: "csv" | "pdf") => {
    if (!baseUrl || !selectedTemplate) return "#";
    const params = new URLSearchParams();
    params.set("template", selectedTemplate.id);
    if (start) params.set("start", start);
    if (end) params.set("end", end);
    params.set("format", format);
    return `${baseUrl}?${params.toString()}`;
  };

  const renderTemplateGroup = (label: string, items: typeof builtIn) => {
    if (!items.length) return null;
    return (
      <div className="mt-4" key={label}>
        <h3 className="text-lg font-semibold">{label}</h3>
        <div className="mt-2 space-y-3">
          {items.map((template) => {
            const inputId = `report-template-${template.id}`;
            return (
              <label
                key={template.id}
                htmlFor={inputId}
                className="block rounded-md border border-slate-200 bg-white p-4 shadow-sm transition hover:border-slate-300 focus-within:border-blue-500 focus-within:ring-2 focus-within:ring-blue-200"
              >
                <div className="flex items-start gap-3">
                  <input
                    type="radio"
                    id={inputId}
                    name="report-template"
                    value={template.id}
                    checked={selectedTemplateId === template.id}
                    onChange={() => setSelectedTemplateId(template.id)}
                    className="mt-1 h-4 w-4"
                  />
                  <div className="flex-1">
                    <div className="font-medium text-slate-900">{template.name}</div>
                    {template.description ? (
                      <p className="mt-1 text-sm text-slate-600">{template.description}</p>
                    ) : null}
                    {fieldList(template.fields, t("reports.templates.fields"))}
                  </div>
                </div>
              </label>
            );
          })}
        </div>
      </div>
    );
  };

  return (
    <div className="container mx-auto p-4 max-w-3xl">
      <h1 className="mb-4 text-2xl md:text-4xl">{t("reports.title")}</h1>
      {ownersLoaded && owners.length === 0 ? (
        <p>{t("reports.noOwners")}</p>
      ) : (
        <OwnerSelector owners={owners} selected={owner} onSelect={setOwner} />
      )}
      <div className="my-4">
        <label className="mr-2">
          {t("query.start")}:{" "}
          <input type="date" value={start} onChange={(e) => setStart(e.target.value)} />
        </label>
        <label>
          {t("query.end")}:{" "}
          <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
        </label>
      </div>
      <section className="mt-6">
        <h2 className="text-xl font-semibold">{t("reports.templates.heading")}</h2>
        <div className="mt-2 space-y-4">
          {catalogLoading ? (
            <p>{t("reports.templates.loading")}</p>
          ) : catalogError ? (
            <p role="alert" className="text-sm text-red-600">
              {t("reports.templates.error")}
            </p>
          ) : availableTemplates.length === 0 ? (
            <p>{t("reports.templates.none")}</p>
          ) : (
            <>
              {renderTemplateGroup(t("reports.templates.builtIn"), builtIn)}
              {renderTemplateGroup(t("reports.templates.custom"), filteredCustomTemplates)}
            </>
          )}
        </div>
      </section>
      {canDownload ? (
        <div className="mt-6 space-x-4 text-blue-700">
          <a href={createDownloadHref("csv")}>{t("reports.csv")}</a>
          <a href={createDownloadHref("pdf")}>{t("reports.pdf")}</a>
        </div>
      ) : (
        <p className="mt-6 text-sm text-slate-600">{t("reports.selectTemplate")}</p>
      )}
    </div>
  );
}

