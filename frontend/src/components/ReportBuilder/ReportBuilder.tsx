import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import type {
  ReportTemplate,
  ReportTemplateInput,
  ReportTemplateSectionInput,
} from "@/types";

import { REPORT_SECTION_OPTIONS } from "./sections";

export interface ReportBuilderProps {
  template?: ReportTemplate;
  onCreate: (input: ReportTemplateInput) => Promise<void>;
  onUpdate?: (id: string, input: ReportTemplateInput) => Promise<void>;
  onDelete?: (id: string) => Promise<void>;
  onCancel: () => void;
}

const defaultSections = (): ReportTemplateSectionInput[] => [
  {
    id: REPORT_SECTION_OPTIONS[0].id,
    columns: REPORT_SECTION_OPTIONS[0].columns.map((column) => column.key),
  },
];

export function ReportBuilder({
  template,
  onCreate,
  onUpdate,
  onDelete,
  onCancel,
}: ReportBuilderProps) {
  const { t } = useTranslation();
  const isEdit = Boolean(template);
  const [name, setName] = useState(template?.name ?? "");
  const [description, setDescription] = useState(template?.description ?? "");
  // Ordered as REPORT_SECTION_OPTIONS so the saved template is stable.
  const [sections, setSections] = useState<ReportTemplateSectionInput[]>(
    template?.sections?.length ? template.sections : defaultSections(),
  );
  const [validationErrors, setValidationErrors] = useState<{
    name?: string;
    metrics?: string;
    columns?: string;
  }>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const sectionOptions = useMemo(
    () =>
      REPORT_SECTION_OPTIONS.map((option) => ({
        ...option,
        label: t(option.labelKey),
        columns: option.columns.map((column) => ({
          ...column,
          label: t(`reports.builder.columns.${column.key}`, column.label),
        })),
      })),
    [t],
  );

  const selectionFor = (id: string) =>
    sections.find((section) => section.id === id);

  const toggleSection = (id: string) => {
    setSections((prev) => {
      if (prev.some((section) => section.id === id)) {
        return prev.filter((section) => section.id !== id);
      }
      const option = REPORT_SECTION_OPTIONS.find((item) => item.id === id);
      const added = {
        id,
        columns: option ? option.columns.map((column) => column.key) : [],
      };
      return REPORT_SECTION_OPTIONS.flatMap((item) => {
        if (item.id === id) return [added];
        const existing = prev.find((section) => section.id === item.id);
        return existing ? [existing] : [];
      });
    });
  };

  const toggleColumn = (sectionId: string, key: string) => {
    setSections((prev) =>
      prev.map((section) => {
        if (section.id !== sectionId) return section;
        const option = REPORT_SECTION_OPTIONS.find((item) => item.id === sectionId);
        const next = section.columns.includes(key)
          ? section.columns.filter((column) => column !== key)
          : [...section.columns, key];
        // Keep the source's own column order regardless of click order.
        const order = option?.columns.map((column) => column.key) ?? next;
        return {
          ...section,
          columns: order.filter((column) => next.includes(column)),
        };
      }),
    );
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setValidationErrors({});
    setFormError(null);

    const trimmedName = name.trim();
    const trimmedDescription = description.trim();

    const nextErrors: { name?: string; metrics?: string; columns?: string } = {};
    if (!trimmedName) {
      nextErrors.name = t("reports.builder.validation.name", "Name is required");
    }
    if (sections.length === 0) {
      nextErrors.metrics = t(
        "reports.builder.validation.metrics",
        "Select at least one section",
      );
    }
    if (sections.some((section) => section.columns.length === 0)) {
      nextErrors.columns = t(
        "reports.builder.validation.columns",
        "Select at least one column for each section",
      );
    }

    if (Object.keys(nextErrors).length > 0) {
      setValidationErrors(nextErrors);
      return;
    }

    const payload: ReportTemplateInput = {
      name: trimmedName,
      description: trimmedDescription ? trimmedDescription : undefined,
      sections,
    };

    try {
      setSubmitting(true);
      if (isEdit && template && onUpdate) {
        await onUpdate(template.id, payload);
      } else {
        await onCreate(payload);
      }
      onCancel();
    } catch (error) {
      console.error("Failed to save report template", error);
      setFormError(
        error instanceof Error
          ? error.message
          : t("reports.builder.saveError", "Unable to save the template. Try again."),
      );
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async () => {
    if (!template || !onDelete) return;
    setDeleteError(null);
    try {
      setDeleting(true);
      await onDelete(template.id);
      onCancel();
    } catch (error) {
      console.error("Failed to delete report template", error);
      setDeleteError(
        error instanceof Error
          ? error.message
          : t("reports.builder.deleteError", "Unable to delete the template. Try again."),
      );
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="max-h-full w-full max-w-3xl overflow-y-auto rounded-lg bg-[var(--surface-card-bg)] p-6 shadow-xl">
        <div className="mb-4 flex items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold" data-testid="report-builder-heading">
              {isEdit
                ? t("reports.builder.headingEdit")
                : t("reports.builder.headingCreate")}
            </h1>
            <p className="text-sm text-[var(--surface-muted-color)]">{t("reports.builder.subheading")}</p>
          </div>
          <button
            type="button"
            onClick={onCancel}
            className="rounded border border-[var(--surface-card-border)] px-3 py-1 text-sm font-medium text-[var(--surface-muted-color)] hover:bg-[var(--menu-hover-bg)]"
          >
            {t("common.close", "Close")}
          </button>
        </div>
        <form className="space-y-6" onSubmit={handleSubmit}>
          <div>
            <label htmlFor="report-template-name" className="block text-sm font-medium text-[var(--surface-muted-color)]">
              {t("reports.builder.nameLabel")}
            </label>
            <input
              id="report-template-name"
              type="text"
              value={name}
              onChange={(event) => setName(event.target.value)}
              disabled={submitting}
              className="mt-1 w-full rounded border border-[var(--surface-card-border)] px-3 py-2 shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
            {validationErrors.name && (
              <p className="mt-1 text-sm text-red-600">{validationErrors.name}</p>
            )}
          </div>

          <div>
            <label
              htmlFor="report-template-description"
              className="block text-sm font-medium text-[var(--surface-muted-color)]"
            >
              {t("reports.builder.descriptionLabel")}
            </label>
            <textarea
              id="report-template-description"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              disabled={submitting}
              className="mt-1 w-full rounded border border-[var(--surface-card-border)] px-3 py-2 shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              rows={2}
            />
          </div>

          <div>
            <p className="text-sm font-medium text-[var(--surface-muted-color)]">
              {t("reports.builder.metricsLabel")}
            </p>
            <div className="mt-2 space-y-2">
              {sectionOptions.map((option) => {
                const selection = selectionFor(option.id);
                return (
                  <div key={option.id} className="rounded border border-[var(--surface-card-border)] p-2">
                    <label className="flex items-center gap-2 font-medium">
                      <input
                        type="checkbox"
                        checked={Boolean(selection)}
                        onChange={() => toggleSection(option.id)}
                        disabled={submitting}
                      />
                      <span>{option.label}</span>
                    </label>
                    {selection ? (
                      <fieldset className="mt-2 pl-6">
                        <legend className="text-xs uppercase tracking-wide text-[var(--surface-muted-color)]">
                          {t("reports.builder.columnsLabel")}
                        </legend>
                        <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1">
                          {option.columns.map((column) => (
                            <label
                              key={column.key}
                              className="flex items-center gap-2 text-sm"
                            >
                              <input
                                type="checkbox"
                                aria-label={`${option.label}: ${column.label}`}
                                checked={selection.columns.includes(column.key)}
                                onChange={() => toggleColumn(option.id, column.key)}
                                disabled={submitting}
                              />
                              <span>{column.label}</span>
                            </label>
                          ))}
                        </div>
                      </fieldset>
                    ) : null}
                  </div>
                );
              })}
            </div>
            {validationErrors.metrics && (
              <p className="mt-1 text-sm text-red-600">{validationErrors.metrics}</p>
            )}
            {validationErrors.columns && (
              <p className="mt-1 text-sm text-red-600">{validationErrors.columns}</p>
            )}
          </div>

          {formError && <p className="text-sm text-red-600">{formError}</p>}
          {deleteError && <p className="text-sm text-red-600">{deleteError}</p>}

          <div className="flex flex-col-reverse gap-3 md:flex-row md:items-center md:justify-between">
            {isEdit && onDelete && (
              <button
                type="button"
                onClick={handleDelete}
                className="rounded border border-red-300 px-4 py-2 text-sm font-medium text-red-700 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-60"
                disabled={deleting || submitting}
              >
                {deleting ? t("reports.builder.deleting") : t("reports.builder.delete")}
              </button>
            )}
            <div className="flex flex-col gap-3 md:flex-row md:items-center md:gap-4">
              <button
                type="button"
                onClick={onCancel}
                className="rounded border border-[var(--surface-card-border)] px-4 py-2 text-sm font-medium text-[var(--surface-muted-color)] hover:bg-[var(--menu-hover-bg)]"
                disabled={submitting || deleting}
              >
                {t("common.cancel", "Cancel")}
              </button>
              <button
                type="submit"
                className="rounded bg-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-70"
                disabled={submitting || deleting}
              >
                {submitting
                  ? t("reports.builder.saving")
                  : isEdit
                  ? t("reports.builder.saveChanges")
                  : t("reports.builder.create")}
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}
