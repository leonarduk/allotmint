import { useEffect, useState } from "react";
import { getQuests, completeQuest } from "../api";
import type { QuestResponse } from "../types";

export default function QuestBoard() {
  const [data, setData] = useState<QuestResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    setError(null);
    getQuests()
      .then(setData)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, []);

  const handleComplete = (id: string) => {
    completeQuest(id)
      .then(setData)
      .catch((e) => setError(String(e)));
  };

  if (loading || !data) return <div>Loading quests...</div>;
  if (error) return <div style={{ color: "red" }}>{error}</div>;

  return (
    <div className="quest-board" style={{ margin: "1rem 0" }}>
      <div className="quest-stats" style={{ marginBottom: "0.5rem" }}>
        <span>XP: {data.xp}</span>
        <span style={{ marginLeft: "1rem" }}>Streak: {data.streak}</span>
      </div>
      <ul style={{ listStyle: "none", padding: 0 }}>
        {data.quests.map((q) => (
          <li key={q.id} style={{ marginBottom: "0.25rem" }}>
            <button
              onClick={() => handleComplete(q.id)}
              disabled={q.completed}
              style={{
                textDecoration: q.completed ? "line-through" : undefined,
              }}
            >
              {q.title} (+{q.xp} XP)
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
