import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import type {
  ReportTemplate,
  ReportTemplateFilter,
  ReportTemplateFilterOperator,
  ReportTemplateInput,
} from "@/types";

const METRIC_OPTIONS = [
  { id: "performance", labelKey: "reports.builder.metrics.performance" },
  { id: "holdings", labelKey: "reports.builder.metrics.holdings" },
  { id: "transactions", labelKey: "reports.builder.metrics.transactions" },
  { id: "risk", labelKey: "reports.builder.metrics.risk" },
];

const COLUMN_OPTIONS = [
  { id: "owner", labelKey: "reports.builder.columns.owner" },
  { id: "account", labelKey: "reports.builder.columns.account" },
  { id: "ticker", labelKey: "reports.builder.columns.ticker" },
  { id: "value_gbp", labelKey: "reports.builder.columns.value" },
  { id: "gain_pct", labelKey: "reports.builder.columns.gain" },
];

const FILTER_FIELDS = [
  { id: "account_type", labelKey: "reports.builder.filters.accountType" },
  { id: "instrument_type", labelKey: "reports.builder.filters.instrumentType" },
  { id: "region", labelKey: "reports.builder.filters.region" },
  { id: "sector", labelKey: "reports.builder.filters.sector" },
];

const OPERATORS: { id: ReportTemplateFilterOperator; labelKey: string }[] = [
  { id: "equals", labelKey: "reports.builder.operators.equals" },
  { id: "not_equals", labelKey: "reports.builder.operators.notEquals" },
  { id: "contains", labelKey: "reports.builder.operators.contains" },
  { id: "gt", labelKey: "reports.builder.operators.gt" },
  { id: "lt", labelKey: "reports.builder.operators.lt" },
];

export interface ReportBuilderProps {
  template?: ReportTemplate;
  onCreate: (input: ReportTemplateInput) => Promise<void>;
  onUpdate?: (id: string, input: ReportTemplateInput) => Promise<void>;
  onDelete?: (id: string) => Promise<void>;
  onCancel: () => void;
}

const hasContent = (value: string) => value.trim().length > 0;

const cleanFilters = (filters: ReportTemplateFilter[]): ReportTemplateFilter[] =>
  filters
    .filter((filter) => hasContent(filter.field) && hasContent(filter.value))
    .map((filter) => ({
      ...filter,
      field: filter.field.trim(),
      value: filter.value.trim(),
    }));

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
  const [selectedMetrics, setSelectedMetrics] = useState<string[]>(
    template?.metrics && template.metrics.length > 0
      ? template.metrics
      : [METRIC_OPTIONS[0].id],
  );
  const [selectedColumns, setSelectedColumns] = useState<string[]>(
    template?.columns && template.columns.length > 0
      ? template.columns
      : COLUMN_OPTIONS.slice(0, 3).map((option) => option.id),
  );
  const [filters, setFilters] = useState<ReportTemplateFilter[]>(
    template?.filters?.length ? template.filters : [],
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

  const metricOptions = useMemo(
    () => METRIC_OPTIONS.map((option) => ({ ...option, label: t(option.labelKey) })),
    [t],
  );
  const columnOptions = useMemo(
    () => COLUMN_OPTIONS.map((option) => ({ ...option, label: t(option.labelKey) })),
    [t],
  );
  const availableFilters = useMemo(
    () => FILTER_FIELDS.map((option) => ({ ...option, label: t(option.labelKey) })),
    [t],
  );
  const operatorOptions = useMemo(
    () => OPERATORS.map((option) => ({ ...option, label: t(option.labelKey) })),
    [t],
  );

  const toggleSelection = (
    value: string,
    selected: string[],
    setSelected: (next: string[]) => void,
  ) => {
    setSelected(
      selected.includes(value)
        ? selected.filter((item) => item !== value)
        : [...selected, value],
    );
  };

  const handleFilterChange = (
    index: number,
    key: keyof ReportTemplateFilter,
    value: string,
  ) => {
    setFilters((prev) => {
      const next = [...prev];
      next[index] = { ...next[index], [key]: value };
      return next;
    });
  };

  const handleAddFilter = () => {
    setFilters((prev) => [
      ...prev,
      {
        field: availableFilters[0]?.id ?? "account_type",
        operator: "equals",
        value: "",
      },
    ]);
  };

  const handleRemoveFilter = (index: number) => {
    setFilters((prev) => prev.filter((_, idx) => idx !== index));
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
    if (selectedMetrics.length === 0) {
      nextErrors.metrics = t(
        "reports.builder.validation.metrics",
        "Select at least one metric",
      );
    }
    if (selectedColumns.length === 0) {
      nextErrors.columns = t(
        "reports.builder.validation.columns",
        "Select at least one column",
      );
    }

    if (Object.keys(nextErrors).length > 0) {
      setValidationErrors(nextErrors);
      return;
    }

    const payload: ReportTemplateInput = {
      name: trimmedName,
      description: trimmedDescription ? trimmedDescription : undefined,
      metrics: selectedMetrics,
      columns: selectedColumns,
      filters: cleanFilters(filters),
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
      <div className="max-h-full w-full max-w-3xl overflow-y-auto rounded-lg bg-white p-6 shadow-xl">
        <div className="mb-4 flex items-start justify-between gap-4">
          <div>
            <h2 className="text-2xl font-semibold" data-testid="report-builder-heading">
              {isEdit
                ? t("reports.builder.headingEdit")
                : t("reports.builder.headingCreate")}
            </h2>
            <p className="text-sm text-gray-600">{t("reports.builder.subheading")}</p>
          </div>
          <button
            type="button"
            onClick={onCancel}
            className="rounded border border-gray-300 px-3 py-1 text-sm font-medium text-gray-700 hover:bg-gray-100"
          >
            {t("common.close", "Close")}
          </button>
        </div>
        <form className="space-y-6" onSubmit={handleSubmit}>
          <div>
            <label htmlFor="report-template-name" className="block text-sm font-medium text-gray-700">
              {t("reports.builder.nameLabel")}
            </label>
            <input
              id="report-template-name"
              type="text"
              value={name}
              onChange={(event) => setName(event.target.value)}
              disabled={submitting}
              className="mt-1 w-full rounded border border-gray-300 px-3 py-2 shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
            {validationErrors.name && (
              <p className="mt-1 text-sm text-red-600">{validationErrors.name}</p>
            )}
          </div>

          <div>
            <label
              htmlFor="report-template-description"
              className="block text-sm font-medium text-gray-700"
            >
              {t("reports.builder.descriptionLabel")}
            </label>
            <textarea
              id="report-template-description"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              disabled={submitting}
              className="mt-1 w-full rounded border border-gray-300 px-3 py-2 shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              rows={2}
            />
          </div>

          <div>
            <p className="text-sm font-medium text-gray-700">
              {t("reports.builder.metricsLabel")}
            </p>
            <div className="mt-2 grid gap-2 md:grid-cols-2">
              {metricOptions.map((option) => (
                <label key={option.id} className="flex items-center gap-2 rounded border border-gray-200 p-2">
                  <input
                    type="checkbox"
                    checked={selectedMetrics.includes(option.id)}
                    onChange={() => toggleSelection(option.id, selectedMetrics, setSelectedMetrics)}
                    disabled={submitting}
                  />
                  <span>{option.label}</span>
                </label>
              ))}
            </div>
            {validationErrors.metrics && (
              <p className="mt-1 text-sm text-red-600">{validationErrors.metrics}</p>
            )}
          </div>

          <div>
            <p className="text-sm font-medium text-gray-700">
              {t("reports.builder.columnsLabel")}
            </p>
            <div className="mt-2 grid gap-2 md:grid-cols-2">
              {columnOptions.map((option) => (
                <label key={option.id} className="flex items-center gap-2 rounded border border-gray-200 p-2">
                  <input
                    type="checkbox"
                    checked={selectedColumns.includes(option.id)}
                    onChange={() => toggleSelection(option.id, selectedColumns, setSelectedColumns)}
                    disabled={submitting}
                  />
                  <span>{option.label}</span>
                </label>
              ))}
            </div>
            {validationErrors.columns && (
              <p className="mt-1 text-sm text-red-600">{validationErrors.columns}</p>
            )}
          </div>

          <div>
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium text-gray-700">
                {t("reports.builder.filtersLabel")}
              </p>
              <button
                type="button"
                onClick={handleAddFilter}
                className="text-sm font-medium text-indigo-600 hover:text-indigo-500"
                disabled={submitting}
              >
                {t("reports.builder.addFilter")}
              </button>
            </div>
            {filters.length === 0 ? (
              <p className="mt-2 text-sm text-gray-500">{t("reports.builder.noFilters")}</p>
            ) : (
              <div className="mt-2 space-y-3">
                {filters.map((filter, index) => (
                  <div
                    key={`filter-${index}`}
                    className="flex flex-col gap-2 rounded border border-gray-200 p-3 md:flex-row md:items-center"
                  >
                    <label className="flex-1 text-sm">
                      <span className="mb-1 block font-medium text-gray-700">
                        {t("reports.builder.filterField")}
                      </span>
                      <select
                        value={filter.field}
                        onChange={(event) => handleFilterChange(index, "field", event.target.value)}
                        className="w-full rounded border border-gray-300 px-2 py-1"
                        disabled={submitting}
                      >
                        {availableFilters.map((field) => (
                          <option key={field.id} value={field.id}>
                            {field.label}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="flex-1 text-sm">
                      <span className="mb-1 block font-medium text-gray-700">
                        {t("reports.builder.filterOperator")}
                      </span>
                      <select
                        value={filter.operator}
                        onChange={(event) =>
                          handleFilterChange(
                            index,
                            "operator",
                            event.target.value as ReportTemplateFilterOperator,
                          )
                        }
                        className="w-full rounded border border-gray-300 px-2 py-1"
                        disabled={submitting}
                      >
                        {operatorOptions.map((operator) => (
                          <option key={operator.id} value={operator.id}>
                            {operator.label}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="flex-1 text-sm">
                      <span className="mb-1 block font-medium text-gray-700">
                        {t("reports.builder.filterValue")}
                      </span>
                      <input
                        type="text"
                        value={filter.value}
                        onChange={(event) => handleFilterChange(index, "value", event.target.value)}
                        className="w-full rounded border border-gray-300 px-2 py-1"
                        disabled={submitting}
                      />
                    </label>
                    <button
                      type="button"
                      onClick={() => handleRemoveFilter(index)}
                      className="self-start rounded border border-red-200 px-3 py-1 text-sm font-medium text-red-600 hover:bg-red-50"
                      disabled={submitting}
                    >
                      {t("reports.builder.removeFilter")}
                    </button>
                  </div>
                ))}
              </div>
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
                className="rounded border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100"
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
