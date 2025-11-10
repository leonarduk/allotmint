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
};

export function useReportsCatalog(): ReportsCatalogResult {
  const fetchCatalog = useCallback(() => listReportTemplates(), []);
  const { data, loading, error } = useFetch(fetchCatalog, []);

  const templates = data ?? [];

  const { builtin, custom } = useMemo(() => {
    const builtinTemplates: ReportTemplateMetadata[] = [];
    const customTemplates: ReportTemplateMetadata[] = [];

    for (const template of templates) {
      if (template.builtin) builtinTemplates.push(template);
      else customTemplates.push(template);
    }

    return { builtin: builtinTemplates, custom: customTemplates };
  }, [templates]);

  return { templates, builtin, custom, loading, error };
}

export default useReportsCatalog;
