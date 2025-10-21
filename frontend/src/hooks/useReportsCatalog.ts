import { useCallback, useEffect, useMemo, useState } from "react";

import { getReportsCatalog, type ReportsCatalogResponse } from "@/api";
import type { ReportTemplate } from "@/types";

export type TemplateSource = "built-in" | "custom";

export type CatalogTemplate = ReportTemplate & { source: TemplateSource };

export type UseReportsCatalogResult = {
  builtIn: ReportTemplate[];
  custom: ReportTemplate[];
  templates: CatalogTemplate[];
  loading: boolean;
  error: Error | null;
  refetch: () => Promise<void>;
};

const normalizeCatalog = (
  response: ReportsCatalogResponse,
): { builtIn: ReportTemplate[]; custom: ReportTemplate[] } => {
  const builtIn = response.builtIn ?? (response as Record<string, unknown>).builtin;
  return {
    builtIn: Array.isArray(builtIn) ? (builtIn as ReportTemplate[]) : [],
    custom: Array.isArray(response.custom) ? response.custom : [],
  };
};

export function useReportsCatalog(): UseReportsCatalogResult {
  const [data, setData] = useState<{ builtIn: ReportTemplate[]; custom: ReportTemplate[] } | null>(
    null,
  );
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const fetchCatalog = useCallback(async () => {
    setLoading(true);
    try {
      const response = await getReportsCatalog();
      const normalized = normalizeCatalog(response);
      setData(normalized);
      setError(null);
    } catch (err) {
      setError(err as Error);
      setData({ builtIn: [], custom: [] });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchCatalog();
  }, [fetchCatalog]);

  const builtIn = data?.builtIn ?? [];
  const custom = data?.custom ?? [];

  const templates = useMemo(() => {
    const withSource = <T extends ReportTemplate>(tpls: T[], source: TemplateSource) =>
      tpls.map((template) => ({ ...template, source } as CatalogTemplate));
    return [...withSource(builtIn, "built-in"), ...withSource(custom, "custom")];
  }, [builtIn, custom]);

  return {
    builtIn,
    custom,
    templates,
    loading,
    error,
    refetch: fetchCatalog,
  };
}

export default useReportsCatalog;
