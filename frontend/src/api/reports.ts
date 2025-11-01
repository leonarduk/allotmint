import { API_BASE, fetchJson } from "@/api";
import type { ReportTemplateMetadata } from "@/types";

const TEMPLATE_BASE = `${API_BASE}/reports/templates`;

export const listReportTemplates = () =>
  fetchJson<ReportTemplateMetadata[]>(TEMPLATE_BASE);
