import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { createGoal, getGoal, getGoals } from "../api";
import { money } from "../lib/money";
import { EMPTY_GOAL_FORM, formatGoalDate, parseGoalForm, type Goal, type GoalForm } from "../lib/goalForm";

type GoalWithProgress = Goal & { progress: number; trades: { action: string; amount: number; ticker: string }[] };

const fieldStyle = { display: "flex", flexDirection: "column" as const, gap: "0.25rem" };

export default function Goals() {
  const { t, i18n } = useTranslation();
  const [goals, setGoals] = useState<Goal[]>([]);
  const [form, setForm] = useState<GoalForm>(EMPTY_GOAL_FORM);
  const [error, setError] = useState<string | null>(null);
  const [current, setCurrent] = useState("");
  const [selected, setSelected] = useState<GoalWithProgress | null>(null);

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
    const amount = Number(current);
    getGoal(name, Number.isFinite(amount) ? amount : 0)
      .then(setSelected)
      .catch(() => setSelected(null));
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
        <p id="goal-form-error" role="alert" style={{ color: "var(--color-danger, #b91c1c)" }}>
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
          <p>
            {t("goals.progress", { progress: Math.round(selected.progress * 100) })}
          </p>
          {selected.trades.length > 0 && (
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
