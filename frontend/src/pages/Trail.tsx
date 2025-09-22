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

  if (error) return <div style={{ color: "red" }}>{error}</div>;
  if (!data) return <div>{t("common.loading")}</div>;

  const daily = data.tasks.filter((t) => t.type === "daily");
  const once = data.tasks.filter((t) => t.type === "once");
  const todayKey = new Date().toISOString().slice(0, 10);
  const completedTodayFromServer = data.daily_totals?.[todayKey] ?? 0;
  const completedDaily = daily.filter((t) => t.completed).length;
  const completedCount = Math.max(completedTodayFromServer, completedDaily);
  const totalDaily = daily.length;
  const clampedCompleted =
    totalDaily > 0 ? Math.min(completedCount, totalDaily) : completedCount;
  const progressPercent =
    totalDaily > 0 ? Math.round((clampedCompleted / totalDaily) * 100) : 0;
  const progressSummary =
    totalDaily > 0
      ? t("trail.progressSummary", {
          completed: clampedCompleted,
          total: totalDaily,
          percent: progressPercent,
        })
      : t("trail.noDailyTasks");
  const showCelebration = totalDaily > 0 && clampedCompleted === totalDaily;

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
      <header
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "1rem",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: "1.5rem",
          border: "1px solid #e5e7eb",
          borderRadius: "0.75rem",
          padding: "1.5rem",
          background: "#f9fafb",
        }}
      >
        <div style={{ flex: "1 1 16rem", minWidth: "16rem" }}>
          <h1 style={{ margin: "0 0 0.5rem" }}>{t("trail.progressHeading")}</h1>
          <p style={{ margin: "0 0 1rem", color: "#4b5563" }}>{progressSummary}</p>
          <div
            role="progressbar"
            aria-valuenow={progressPercent}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={t("trail.progressHeading")}
            style={{
              width: "100%",
              height: "0.75rem",
              borderRadius: "999px",
              background: "#e5e7eb",
              overflow: "hidden",
            }}
          >
            <div
              style={{
                width: `${progressPercent}%`,
                height: "100%",
                background: showCelebration ? "#22c55e" : "#3b82f6",
                transition: "width 0.3s ease",
              }}
            />
          </div>
        </div>
        <div
          style={{
            display: "flex",
            gap: "1rem",
            alignItems: "center",
            justifyContent: "flex-end",
            flex: "0 0 auto",
          }}
        >
          <div
            style={{
              padding: "0.75rem 1rem",
              borderRadius: "0.75rem",
              background: "#eef2ff",
              textAlign: "center",
              minWidth: "6rem",
            }}
          >
            <div style={{ fontSize: "0.8rem", color: "#4338ca" }}>
              {t("trail.xpTitle")}
            </div>
            <div style={{ fontWeight: 700, color: "#1e1b4b" }}>
              {t("trail.xpLabel", { xp: data.xp })}
            </div>
          </div>
          <div
            style={{
              padding: "0.75rem 1rem",
              borderRadius: "999px",
              background: "#fef3c7",
              textAlign: "center",
              minWidth: "8rem",
            }}
          >
            <div style={{ fontSize: "0.8rem", color: "#b45309" }}>
              {t("trail.streakTitle")}
            </div>
            <div style={{ fontWeight: 700, color: "#92400e" }}>
              {t("trail.streakLabel", { count: data.streak })}
            </div>
          </div>
        </div>
      </header>

      {showCelebration && (
        <div
          role="status"
          aria-live="polite"
          style={{
            marginBottom: "1.5rem",
            padding: "1rem 1.25rem",
            borderRadius: "0.75rem",
            background: "#ecfccb",
            color: "#3f6212",
            fontWeight: 600,
          }}
        >
          {t("trail.celebration")}
        </div>
      )}

      {renderSection(daily, t("trail.daily"))}
      {renderSection(once, t("trail.once"))}
    </div>
  );
}
