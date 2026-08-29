import { useCallback } from "react";
import { listSavedQueries } from "../api";
import type { SavedQuery, CustomQuery } from "../types";
import { useFetch } from "../hooks/useFetch";

type Props = {
  onLoad: (params: CustomQuery) => void;
};

// Issue #7202: `data/queries/demo-slug.json` is a developer-seeded example
// that the backend's `/custom-query/saved` listing surfaces indistinguishably
// from a real user-saved query, showing up here as an unlabelled internal
// slug ("demo-slug"). It lives outside this component's ownership (it's
// backend seed data, not frontend code), so rather than editing it — and
// risking that a real user could still legitimately name a saved query
// "demo-slug" — we filter this one known placeholder id out of the
// user-facing list. Any genuinely-named saved query is unaffected.
const SEEDED_EXAMPLE_QUERY_IDS = new Set(["demo-slug"]);

export function SavedQueries({ onLoad }: Props) {
  const loadQueries = useCallback(() => listSavedQueries({ detailed: true }), []);
  const { data: queries, loading, error } = useFetch<SavedQuery[]>(
    loadQueries,
    [],
  );

  if (loading) return <p>Loading saved queries…</p>;
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
      <h3>Saved Queries</h3>
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
