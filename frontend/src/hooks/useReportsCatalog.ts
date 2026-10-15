import { useCallback, useMemo } from "react";

import { listReportTemplates } from "@/api/reports";
import type { ReportTemplateMetadata } from "@/types";

import useFetch from "./useFetch";

type ReportsCatalogResult = {
  templates: ReportTemplateMetadata[];
  builtin: ReportTemplateMetadata[];
  custom: ReportTemplateMetadata[];
  loading: boolean;
  error: Error | null;
  /** Re-read the catalogue, e.g. after a custom template is deleted. */
  refetch: () => void;
};

export function useReportsCatalog(): ReportsCatalogResult {
  const fetchCatalog = useCallback(() => listReportTemplates(), []);
  const { data, loading, error, refetch } = useFetch(fetchCatalog, []);

  const templates = useMemo(() => data ?? [], [data]);

  const { builtin, custom } = useMemo(() => {
    const builtinTemplates: ReportTemplateMetadata[] = [];
    const customTemplates: ReportTemplateMetadata[] = [];

    for (const template of templates) {
      if (template.builtin) builtinTemplates.push(template);
      else customTemplates.push(template);
    }

    return { builtin: builtinTemplates, custom: customTemplates };
  }, [templates]);

  return { templates, builtin, custom, loading, error, refetch };
}

export default useReportsCatalog;
