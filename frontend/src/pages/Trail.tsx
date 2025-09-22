import { useEffect, useMemo, useState } from "react";
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

  const tasks = data?.tasks ?? [];
  const daily = useMemo(
    () => tasks.filter((t) => t.type === "daily"),
    [tasks],
  );
  const once = useMemo(
    () => tasks.filter((t) => t.type === "once"),
    [tasks],
  );
  const completedDaily = data?.today_completed ?? daily.filter((t) => t.completed).length;
  const totalDaily = data?.today_total ?? daily.length;
  const completionRatio = totalDaily > 0 ? completedDaily / totalDaily : 0;
  const completionPercent = Math.round(completionRatio * 100);
  const allDailyDone = totalDaily > 0 && completedDaily >= totalDaily;

  if (error) return <div style={{ color: "red" }}>{error}</div>;
  if (!data) return <div>{t("common.loading")}</div>;

  const streakLabel = data.streak
    ? t("trail.streak_value", { count: data.streak })
    : t("trail.streak_none");

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
    <div style={{ margin: "1rem", display: "grid", gap: "1.5rem" }}>
      <section
        aria-label={t("trail.progress_label")}
        style={{
          backgroundColor: "#f5f5f5",
          padding: "1rem",
          borderRadius: "0.75rem",
          display: "grid",
          gap: "0.75rem",
        }}
      >
        <header
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: "1rem",
            alignItems: "baseline",
            justifyContent: "space-between",
          }}
        >
          <div style={{ fontWeight: 600 }}>{t("trail.xp_total", { count: data.xp })}</div>
          <div
            style={{
              padding: "0.25rem 0.75rem",
              borderRadius: "999px",
              backgroundColor: "#fff",
              border: "1px solid #ddd",
              fontSize: "0.9rem",
            }}
          >
            <strong>{t("trail.streak_label")}:</strong> {streakLabel}
          </div>
        </header>
        <div>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              fontSize: "0.95rem",
              marginBottom: "0.4rem",
              gap: "0.75rem",
              flexWrap: "wrap",
            }}
          >
            <span>{t("trail.progress_label")}</span>
            <span>
              {t("trail.progress_summary", {
                completed: completedDaily,
                total: totalDaily,
                percent: completionPercent,
              })}
            </span>
          </div>
          <div
            style={{
              width: "100%",
              height: "12px",
              backgroundColor: "#e0e0e0",
              borderRadius: "999px",
              overflow: "hidden",
            }}
            role="progressbar"
            aria-valuenow={completionPercent}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={t("trail.progress_label")}
          >
            <div
              style={{
                height: "100%",
                width: `${completionPercent}%`,
                background: "linear-gradient(90deg, #4caf50, #81c784)",
                transition: "width 0.3s ease",
              }}
            />
          </div>
        </div>
        {allDailyDone && (
          <div
            role="status"
            aria-live="polite"
            style={{
              backgroundColor: "#e8f5e9",
              border: "1px solid #c8e6c9",
              padding: "0.75rem",
              borderRadius: "0.5rem",
            }}
          >
            {t("trail.all_complete")}
          </div>
        )}
      </section>

      {renderSection(daily, t("trail.daily"))}
      {renderSection(once, t("trail.once"))}
    </div>
  );
}
