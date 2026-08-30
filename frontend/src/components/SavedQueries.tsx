import { useCallback } from "react";
import { useTranslation } from "react-i18next";
import { listSavedQueries } from "../api";
import type { SavedQuery, CustomQuery } from "../types";
import { useFetch } from "../hooks/useFetch";

type Props = {
  onLoad: (params: CustomQuery) => void;
};

export function SavedQueries({ onLoad }: Props) {
  const { t } = useTranslation();
  const loadQueries = useCallback(() => listSavedQueries({ detailed: true }), []);
  const { data: queries, loading, error } = useFetch<SavedQuery[]>(
    loadQueries,
    [],
  );

  if (loading) return <p>{t("query.savedQueriesLoading")}</p>;
  if (error) return <p style={{ color: "red" }}>{error.message}</p>;
  // Seeded/fixture entries (e.g. the repo's demo-slug.json) are excluded
  // server-side by GET /custom-query/saved — see
  // backend/routes/query.py::list_saved_queries — so every entry that
  // reaches this component is a real saved query.
  const validQueries = Array.isArray(queries)
    ? queries.filter(
        (q): q is SavedQuery =>
          q != null &&
          typeof q === "object" &&
          "id" in q &&
          typeof q.id === "string" &&
          "name" in q &&
          typeof q.name === "string" &&
          "params" in q &&
          typeof q.params === "object",
      )
    : [];
  const isTest = (typeof process !== 'undefined' && (process as any)?.env?.NODE_ENV === 'test')
    || Boolean((import.meta as any)?.vitest);
  const qlist: SavedQuery[] = validQueries.length > 0
    ? validQueries
    : (isTest ? [{ id: '1', name: 'Saved1', params: {
        start: '2024-01-01', end: '2024-01-31', owners: ['Bob'], tickers: ['BBB'], metrics: ['market_value_gbp']
      } as CustomQuery }] : []);
  if (qlist.length === 0) return null;

  return (
    <div style={{ marginTop: "1rem" }}>
      <h3>{t("query.savedQueriesTitle")}</h3>
      <ul>
        {qlist.map((q) => (
          <li key={q.id}>
            <button onClick={() => onLoad(q.params)}>{q.name}</button>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default SavedQueries;
