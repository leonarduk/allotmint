import { API_BASE, fetchJson } from "@/api";
import type {
  ReportTemplate,
  ReportTemplateInput,
} from "@/types";

const TEMPLATE_BASE = `${API_BASE}/report-templates`;

const jsonHeaders = { "Content-Type": "application/json" } as const;

export const listReportTemplates = () =>
  fetchJson<ReportTemplate[]>(TEMPLATE_BASE);

export const createReportTemplate = (payload: ReportTemplateInput) =>
  fetchJson<ReportTemplate>(TEMPLATE_BASE, {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify(payload),
  });

export const updateReportTemplate = (
  id: string,
  payload: ReportTemplateInput,
) =>
  fetchJson<ReportTemplate>(`${TEMPLATE_BASE}/${encodeURIComponent(id)}`, {
    method: "PUT",
    headers: jsonHeaders,
    body: JSON.stringify(payload),
  });

export const deleteReportTemplate = (id: string) =>
  fetchJson<void>(`${TEMPLATE_BASE}/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });

export const getReportTemplate = (id: string) =>
  fetchJson<ReportTemplate>(`${TEMPLATE_BASE}/${encodeURIComponent(id)}`);
