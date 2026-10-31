import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { createGoal, getGoal, getGoals, recordGoalProgress } from "../api";
import { money } from "../lib/money";
import { EMPTY_GOAL_FORM, formatGoalDate, parseGoalForm, type Goal, type GoalForm } from "../lib/goalForm";
import { parseCurrentAmount, progressPercent, type GoalDetail, type GoalProjection } from "../lib/goalProgress";

const fieldStyle = { display: "flex", flexDirection: "column" as const, gap: "0.25rem" };

/** Projection sentence plus the assumptions it rests on; nothing is projected without enough history. */
function ProjectionNote({ projection, targetDate }: { projection: GoalProjection | null; targetDate: string }) {
  const { t, i18n } = useTranslation();
  if (!projection) return null;
  const fmt = (iso: string | null) => (iso ? formatGoalDate(iso, i18n.language) : "");
  switch (projection.status) {
    case "reached":
      return <p>{t("goals.projection.reached")}</p>;
    case "not_progressing":
      return <p>{t("goals.projection.notProgressing")}</p>;
    case "insufficient_history":
      return <p>{t("goals.projection.insufficientHistory", { points: projection.min_points, days: projection.min_days })}</p>;
    case "projected":
      return (
        <>
          <p>
            {t(projection.on_track ? "goals.projection.onTrack" : "goals.projection.behind", {
              date: fmt(projection.projected_date),
              targetDate: fmt(targetDate),
            })}
          </p>
          <p>
            <small>
              {t("goals.projection.assumptions", {
                start: fmt(projection.history_start),
                end: fmt(projection.history_end),
                rate: money(projection.monthly_rate, "GBP", i18n.language),
                points: projection.points,
              })}
            </small>
          </p>
        </>
      );
    default:
      return null;
  }
}

export default function Goals() {
  const { t, i18n } = useTranslation();
  const [goals, setGoals] = useState<Goal[]>([]);
  const [form, setForm] = useState<GoalForm>(EMPTY_GOAL_FORM);
  const [error, setError] = useState<string | null>(null);
  const [current, setCurrent] = useState("");
  const [selected, setSelected] = useState<GoalDetail | null>(null);

  const refresh = () => {
    getGoals().then(setGoals).catch(() => setGoals([]));
  };

  useEffect(() => {
    refresh();
  }, []);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const goal = parseGoalForm(form);
    if (!goal) {
      // Keep the form as typed so the user can correct it.
      setError(t("goals.errorRequired"));
      return;
    }
    setError(null);
    createGoal(goal)
      .then(() => {
        setForm(EMPTY_GOAL_FORM);
        refresh();
      })
      .catch((err: unknown) => {
        console.error("Failed to create goal", err);
        setError(t("goals.errorSave"));
      });
  };

  const view = (name: string) => {
    // An entered amount is recorded (dated today) to build the history the
    // projection needs; with no amount, show the latest recorded one.
    const amount = parseCurrentAmount(current);
    (amount === null ? getGoal(name) : recordGoalProgress(name, amount))
      .then(setSelected)
      .catch((err: unknown) => {
        console.error("Failed to load goal", err);
        setSelected(null);
      });
  };

  return (
    <div className="container mx-auto max-w-3xl p-4">
      <h1>{t("goals.title")}</h1>
      <form
        onSubmit={submit}
        noValidate
        aria-describedby={error ? "goal-form-error" : undefined}
        style={{ display: "flex", flexWrap: "wrap", gap: "1rem", alignItems: "flex-end", marginBottom: "1rem" }}
      >
        <label htmlFor="goal-name" style={fieldStyle}>
          {t("common.name")}
          <input
            id="goal-name"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            required
          />
        </label>
        <label htmlFor="goal-target-amount" style={fieldStyle}>
          {t("goals.targetAmount")}
          <input
            id="goal-target-amount"
            type="number"
            min="0"
            step="any"
            inputMode="decimal"
            value={form.target_amount}
            onChange={(e) => setForm({ ...form, target_amount: e.target.value })}
            required
          />
        </label>
        <label htmlFor="goal-target-date" style={fieldStyle}>
          {t("goals.targetDate")}
          <input
            id="goal-target-date"
            type="date"
            value={form.target_date}
            onChange={(e) => setForm({ ...form, target_date: e.target.value })}
            required
          />
        </label>
        <button type="submit">{t("goals.add")}</button>
      </form>
      {error && (
        <p id="goal-form-error" role="alert" style={{ color: "var(--gain-negative)" }}>
          {error}
        </p>
      )}

      <div style={{ marginBottom: "1rem" }}>
        <label htmlFor="goal-current-amount" style={fieldStyle}>
          {t("goals.currentAmount")}
          <input
            id="goal-current-amount"
            type="number"
            min="0"
            step="any"
            inputMode="decimal"
            value={current}
            aria-describedby="goal-current-amount-hint"
            onChange={(e) => setCurrent(e.target.value)}
            style={{ maxWidth: "12rem" }}
          />
        </label>
        <small id="goal-current-amount-hint">{t("goals.currentAmountHint")}</small>
      </div>

      {goals.length === 0 ? (
        <p>{t("goals.empty")}</p>
      ) : (
        <ul>
          {goals.map((g) => (
            <li key={g.name} style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <span>
                {t("goals.goalLine", {
                  name: g.name,
                  amount: money(g.target_amount, "GBP", i18n.language),
                  date: formatGoalDate(g.target_date, i18n.language),
                })}
              </span>
              <button type="button" onClick={() => view(g.name)}>
                {t("goals.view")}
              </button>
            </li>
          ))}
        </ul>
      )}

      {selected && (
        <div style={{ marginTop: "1rem" }}>
          <h2>{selected.name}</h2>
          {selected.progress === null || selected.current_amount === null ? (
            <p>{t("goals.progressUnknown")}</p>
          ) : (
            <>
              <progress
                value={progressPercent(selected.progress)}
                max={100}
                aria-label={t("goals.progressLabel", { name: selected.name })}
                style={{ width: "100%" }}
              />
              <p>
                {t("goals.progressSummary", {
                  current: money(selected.current_amount, "GBP", i18n.language),
                  target: money(selected.target_amount, "GBP", i18n.language),
                  progress: progressPercent(selected.progress),
                })}
              </p>
            </>
          )}
          <ProjectionNote projection={selected.projection} targetDate={selected.target_date} />
          {selected.trades && selected.trades.length > 0 && (
            <>
              <h3>{t("goals.suggestedTrades")}</h3>
              <ul>
                {selected.trades.map((trade, i) => (
                  <li key={i}>
                    {t("goals.trade", {
                      action: trade.action,
                      amount: money(trade.amount, "GBP", i18n.language),
                      ticker: trade.ticker,
                    })}
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}

      <p style={{ marginTop: "2rem" }}>
        <Link to="/">{t("goals.back")}</Link>
      </p>
    </div>
  );
}
