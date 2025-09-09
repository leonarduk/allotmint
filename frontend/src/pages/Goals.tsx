import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { createGoal, getGoal, getGoals } from "../api";

type Goal = {
  name: string;
  target_amount: number;
  target_date: string;
};

type GoalWithProgress = Goal & { progress: number; trades: { action: string; amount: number; ticker: string }[] };

export default function Goals() {
  const { t } = useTranslation();
  const [goals, setGoals] = useState<Goal[]>([]);
  const [form, setForm] = useState<Goal>({ name: "", target_amount: 0, target_date: "" });
  const [current, setCurrent] = useState(0);
  const [selected, setSelected] = useState<GoalWithProgress | null>(null);

  const refresh = () => {
    getGoals().then(setGoals).catch(() => setGoals([]));
  };

  useEffect(() => {
    refresh();
  }, []);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    createGoal(form).then(() => {
      setForm({ name: "", target_amount: 0, target_date: "" });
      refresh();
    });
  };

  const view = (name: string) => {
    getGoal(name, current).then(setSelected).catch(() => setSelected(null));
  };

  return (
    <div style={{ padding: "1rem" }}>
      <h1>{t("goals.title")}</h1>
      <form onSubmit={submit} style={{ marginBottom: "1rem" }}>
        <input
          placeholder={t("common.name")}
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
          required
        />
        <input
          type="number"
          placeholder={t("goals.targetAmount")}
          value={form.target_amount}
          onChange={(e) => setForm({ ...form, target_amount: parseFloat(e.target.value) })}
          required
        />
        <input
          type="date"
          value={form.target_date}
          onChange={(e) => setForm({ ...form, target_date: e.target.value })}
          required
        />
        <button type="submit">{t("goals.add")}</button>
      </form>

      <div style={{ marginBottom: "1rem" }}>
        <label>
          {t("goals.currentAmount")}
          <input
            type="number"
            value={current}
            onChange={(e) => setCurrent(parseFloat(e.target.value))}
          />
        </label>
      </div>

      <ul>
        {goals.map((g) => (
          <li key={g.name}>
            {t("goals.goalLine", {
              name: g.name,
              amount: g.target_amount,
              date: g.target_date,
            })}
            <button onClick={() => view(g.name)} style={{ marginLeft: "0.5rem" }}>
              {t("goals.view")}
            </button>
          </li>
        ))}
      </ul>

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
                      amount: trade.amount,
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
