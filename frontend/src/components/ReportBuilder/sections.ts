import type {
  ReportTemplateColumnMetadata,
  ReportTemplateInput,
} from "@/types";

/**
 * Sections a custom report template can include. Each maps onto one backend
 * section source (`SECTION_BUILDERS` in backend/reports.py) and offers only the
 * columns that source's rows actually carry, so a saved template downloads
 * real data rather than blank cells (#10914).
 */
export interface ReportSectionOption {
  id: string;
  source: string;
  labelKey: string;
  columns: ReportTemplateColumnMetadata[];
}

export const REPORT_SECTION_OPTIONS: ReportSectionOption[] = [
  {
    id: "performance",
    source: "performance.metrics",
    labelKey: "reports.builder.metrics.performance",
    columns: [
      { key: "metric", label: "Metric", type: "string" },
      { key: "value", label: "Value", type: "number" },
      { key: "units", label: "Units", type: "string" },
    ],
  },
  {
    id: "holdings",
    source: "allocation",
    labelKey: "reports.builder.metrics.holdings",
    columns: [
      { key: "ticker", label: "Ticker", type: "string" },
      { key: "exchange", label: "Exchange", type: "string" },
      { key: "units", label: "Units", type: "number" },
      { key: "price", label: "Price", type: "number" },
      { key: "value", label: "Value", type: "number" },
    ],
  },
  {
    id: "transactions",
    source: "transactions",
    labelKey: "reports.builder.metrics.transactions",
    columns: [
      { key: "date", label: "Date", type: "date" },
      { key: "type", label: "Type", type: "string" },
      { key: "description", label: "Description", type: "string" },
      { key: "amount_gbp", label: "Amount (GBP)", type: "number" },
      { key: "currency", label: "Currency", type: "string" },
    ],
  },
  {
    id: "risk",
    source: "performance.risk",
    labelKey: "reports.builder.metrics.risk",
    columns: [
      { key: "metric", label: "Metric", type: "string" },
      { key: "value", label: "Value", type: "number" },
      { key: "window", label: "Window", type: "string" },
      { key: "peak_date", label: "Peak", type: "date" },
      { key: "trough_date", label: "Trough", type: "date" },
    ],
  },
];

export const findSectionOption = (id: string) =>
  REPORT_SECTION_OPTIONS.find((option) => option.id === id);

/**
 * Turn a template name into an id the backend accepts and that stays valid as
 * a report download URL segment: letters, digits, dashes, underscores, max 64.
 */
export function slugifyTemplateId(name: string): string {
  const slug = name
    .normalize("NFKD")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 64)
    .replace(/-+$/g, "");
  return slug || "custom-template";
}

export interface ReportTemplatePayload {
  template_id: string;
  name: string;
  description?: string;
  sections: {
    id: string;
    title: string;
    source: string;
    columns: ReportTemplateColumnMetadata[];
  }[];
}

/**
 * Build the `POST /reports/templates` body from the builder's input. Section
 * titles use `sectionTitle` (the translated label the user saw).
 */
export function buildTemplatePayload(
  input: ReportTemplateInput,
  sectionTitle: (option: ReportSectionOption) => string,
): ReportTemplatePayload {
  const sections = input.sections.map((selection) => {
    const option = findSectionOption(selection.id);
    if (!option) {
      throw new Error(`Unknown report section '${selection.id}'`);
    }
    return {
      id: option.id,
      title: sectionTitle(option),
      source: option.source,
      columns: option.columns.filter((column) =>
        selection.columns.includes(column.key),
      ),
    };
  });
  return {
    template_id: slugifyTemplateId(input.name),
    name: input.name,
    ...(input.description ? { description: input.description } : {}),
    sections,
  };
}
