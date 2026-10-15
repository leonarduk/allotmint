import { API_BASE, fetchJson, fetchText } from "@/api";
import type { ReportTemplatePayload } from "@/components/ReportBuilder/sections";
import type { ReportTemplateMetadata } from "@/types";

const TEMPLATE_BASE = `${API_BASE}/reports/templates`;

export const listReportTemplates = () =>
  fetchJson<ReportTemplateMetadata[]>(TEMPLATE_BASE);

/** Persist a custom template; the backend rejects ids that clash (400). */
export const createReportTemplate = (payload: ReportTemplatePayload) =>
  fetchJson<ReportTemplateMetadata>(TEMPLATE_BASE, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

/** Delete a custom template. Built-ins are refused by the backend (400). */
export const deleteReportTemplate = async (templateId: string) => {
  // 204 No Content: there is no JSON body to parse.
  await fetchText(`${TEMPLATE_BASE}/${encodeURIComponent(templateId)}`, {
    method: "DELETE",
  });
};
