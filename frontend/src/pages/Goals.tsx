import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { createGoal, getGoal, getGoals } from "../api";

type Goal = {
  name: string;
  target_amount: number;
  target_date: string;
};

type GoalWithProgress = Goal & { progress: number; trades: { action: string; amount: number; ticker: string }[] };

export default function Goals() {
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
      <h1>Goals</h1>
      <form onSubmit={submit} style={{ marginBottom: "1rem" }}>
        <input
          placeholder="Name"
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
          required
        />
        <input
          type="number"
          placeholder="Target Amount"
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
        <button type="submit">Add Goal</button>
      </form>

      <div style={{ marginBottom: "1rem" }}>
        <label>
          Current Amount:
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
            {g.name} – target {g.target_amount} by {g.target_date}
            <button onClick={() => view(g.name)} style={{ marginLeft: "0.5rem" }}>
              View
            </button>
          </li>
        ))}
      </ul>

      {selected && (
        <div style={{ marginTop: "1rem" }}>
          <h2>{selected.name}</h2>
          <p>Progress: {Math.round(selected.progress * 100)}%</p>
          {selected.trades.length > 0 && (
            <>
              <h3>Suggested Trades</h3>
              <ul>
                {selected.trades.map((t, i) => (
                  <li key={i}>
                    {t.action} {t.amount} of {t.ticker}
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}

      <p style={{ marginTop: "2rem" }}>
        <Link to="/">Back to Portfolio</Link>
      </p>
    </div>
  );
}
