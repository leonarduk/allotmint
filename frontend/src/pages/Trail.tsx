import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { getTrailTasks, completeTrailTask } from "../api";
import type { TrailResponse } from "../types";

export default function Trail() {
  const { t } = useTranslation();
  const [data, setData] = useState<TrailResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getTrailTasks()
      .then(setData)
      .catch((e) => setError(String(e)));
  }, []);

  const handleToggle = (id: string) => {
    completeTrailTask(id)
      .then(setData)
      .catch((e) => setError(String(e)));
  };

  if (!data) return <div>{t("common.loading")}</div>;
  if (error) return <div style={{ color: "red" }}>{error}</div>;

  const daily = data.tasks.filter((t) => t.type === "daily");
  const once = data.tasks.filter((t) => t.type === "once");

  const renderSection = (items: typeof data.tasks, label: string) => (
    <section>
      <h2>{label}</h2>
      <ul style={{ listStyle: "none", padding: 0 }}>
        {items.map((task) => (
          <li key={task.id} style={{ marginBottom: "0.5rem" }}>
            <button
              onClick={() => handleToggle(task.id)}
              disabled={task.completed}
              style={{
                textDecoration: task.completed ? "line-through" : undefined,
              }}
            >
              {task.title}
            </button>
            {task.commentary && (
              <div style={{ fontSize: "0.8rem" }}>{task.commentary}</div>
            )}
          </li>
        ))}
      </ul>
    </section>
  );

  return (
    <div style={{ margin: "1rem" }}>
      {renderSection(daily, t("trail.daily"))}
      {renderSection(once, t("trail.once"))}
    </div>
  );
}
