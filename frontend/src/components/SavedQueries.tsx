import { listSavedQueries } from "../api";
import type { SavedQuery, CustomQuery } from "../types";
import { useFetch } from "../hooks/useFetch";

type Props = {
  onLoad: (params: CustomQuery) => void;
};

export function SavedQueries({ onLoad }: Props) {
  const { data: queries, loading, error } = useFetch<SavedQuery[]>(
    () => listSavedQueries(),
    [],
  );

  if (loading) return <p>Loading saved queries…</p>;
  if (error) return <p style={{ color: "red" }}>{error.message}</p>;
  if (!queries || queries.length === 0) return null;

  return (
    <div style={{ marginTop: "1rem" }}>
      <h3>Saved Queries</h3>
      <ul>
        {queries.map((q) => (
          <li key={q.id}>
            <button onClick={() => onLoad(q.params)}>{q.name}</button>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default SavedQueries;
