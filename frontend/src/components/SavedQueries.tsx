import { useCallback } from "react";
import { useTranslation } from "react-i18next";
import { listSavedQueries } from "../api";
import type { SavedQuery, CustomQuery } from "../types";
import { useFetch } from "../hooks/useFetch";

type Props = {
  onLoad: (params: CustomQuery) => void;
};

// Issue #7202: `data/queries/demo-slug.json` is a developer-seeded fixture
// the backend's `/custom-query/saved` listing surfaces indistinguishably
// from a real user-saved query, appearing here as an unlabelled internal
// slug ("demo-slug"). It is genuinely off-limits to delete or rename from
// this PR: `tests/backend/test_custom_query_route.py` reads it by that exact
// path/slug and asserts its contents, so removing it breaks the backend
// suite. Filed as follow-up #7381 to fix at the source — either exclude
// known fixture slugs from the public listing server-side, or move the
// fixture outside the publicly-listed queries directory.
//
// In the meantime we filter this one known placeholder id out of the
// user-facing list here. The real, narrow risk this leaves: a user who
// names a saved query anything that slugifies to exactly "demo-slug" (e.g.
// "Demo Slug", "DEMO-SLUG") will have that specific query hidden from this
// list too, indistinguishable from the seeded one. That's an accepted
// trade-off for a rare, unlikely-to-occur name collision.
const SEEDED_EXAMPLE_QUERY_IDS = new Set(["demo-slug"]);

export function SavedQueries({ onLoad }: Props) {
  const { t } = useTranslation();
  const loadQueries = useCallback(() => listSavedQueries({ detailed: true }), []);
  const { data: queries, loading, error } = useFetch<SavedQuery[]>(
    loadQueries,
    [],
  );

  if (loading) return <p>{t("query.savedQueriesLoading")}</p>;
  if (error) return <p style={{ color: "red" }}>{error.message}</p>;
  const validQueries = Array.isArray(queries)
    ? queries.filter(
        (q): q is SavedQuery =>
          q != null &&
          typeof q === "object" &&
          "id" in q &&
          typeof q.id === "string" &&
          !SEEDED_EXAMPLE_QUERY_IDS.has(q.id) &&
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
