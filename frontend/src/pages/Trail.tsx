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
  const todaySummary =
    data.daily_totals?.[data.today] ?? {
      completed: daily.filter((task) => task.completed).length,
      total: daily.length,
    };
  const percent = todaySummary.total
    ? Math.round((todaySummary.completed / todaySummary.total) * 100)
    : 0;
  const allDailyComplete =
    todaySummary.total > 0 && todaySummary.completed === todaySummary.total;
  const allTasksComplete = data.tasks.every((task) => task.completed);
  const progressLabel = t("trail.progressLabel", {
    completed: todaySummary.completed,
    total: todaySummary.total,
    percent,
  });
  const xpLabel = t("trail.xpLabel", { xp: data.xp });
  const streakLabel = t("trail.streakLabel", { count: data.streak });

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
                padding: "0.5rem 0.75rem",
                borderRadius: "0.5rem",
                border: "1px solid #ccc",
                background: task.completed ? "#e6f4ea" : "#fff",
                cursor: task.completed ? "default" : "pointer",
              }}
            >
              {task.title}
            </button>
            {task.commentary && (
              <div style={{ fontSize: "0.8rem", marginTop: "0.25rem" }}>
                {task.commentary}
              </div>
            )}
          </li>
        ))}
      </ul>
    </section>
  );

  return (
    <div style={{ margin: "1rem" }}>
      <header style={{ marginBottom: "1.5rem" }}>
        <h1 style={{ marginBottom: "0.75rem" }}>{t("trail.title")}</h1>
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: "1rem",
            alignItems: "center",
          }}
        >
          <div style={{ flex: "1 1 220px" }}>
            <div
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={todaySummary.total}
              aria-valuenow={todaySummary.completed}
              aria-valuetext={progressLabel}
              style={{
                background: "#f1f3f4",
                borderRadius: "999px",
                height: "0.75rem",
                overflow: "hidden",
              }}
            >
              <div
                style={{
                  width: `${Math.min(percent, 100)}%`,
                  background: "#0f9d58",
                  height: "100%",
                  transition: "width 0.3s ease",
                }}
              />
            </div>
            <div style={{ fontSize: "0.85rem", marginTop: "0.35rem" }}>
              {progressLabel}
            </div>
          </div>
          <div style={{ fontWeight: 600 }}>{xpLabel}</div>
          <div
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "0.35rem",
              padding: "0.35rem 0.6rem",
              borderRadius: "999px",
              background: "#fde68a",
              fontWeight: 600,
            }}
            aria-label={streakLabel}
          >
            <span role="img" aria-hidden="true">
              🔥
            </span>
            <span>{streakLabel}</span>
          </div>
        </div>
        {(allDailyComplete || allTasksComplete) && (
          <div
            role="status"
            aria-live="polite"
            style={{
              marginTop: "1rem",
              padding: "0.75rem",
              borderRadius: "0.75rem",
              background: "#e8f5e9",
              color: "#1b5e20",
            }}
          >
            {allDailyComplete && <div>{t("trail.dailyComplete")}</div>}
            {allTasksComplete && <div>{t("trail.allDone")}</div>}
          </div>
        )}
      </header>
      {renderSection(daily, t("trail.daily"))}
      {renderSection(once, t("trail.once"))}
    </div>
  );
}
