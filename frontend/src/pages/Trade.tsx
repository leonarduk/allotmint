import { useState } from "react";
import { validateTrade } from "../api";
import type { Transaction } from "../types";

export default function Trade() {
  const [tx, setTx] = useState<Transaction>({
    owner: "",
    account: "",
    ticker: "",
    type: "buy",
    date: new Date().toISOString().slice(0, 10),
  });
  const [errors, setErrors] = useState<string[]>([]);
  const [status, setStatus] = useState<string | null>(null);

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>,
  ) => {
    setTx({ ...tx, [e.target.name]: e.target.value });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setStatus(null);
    try {
      const res = await validateTrade(tx);
      if (res.warnings.length) {
        setErrors(res.warnings);
        return;
      }
      setErrors([]);
      setStatus("Trade valid");
      // submit trade here
    } catch (err) {
      setErrors([String(err)]);
    }
  };

  return (
    <form onSubmit={handleSubmit} style={{ maxWidth: 400, margin: "1rem auto" }}>
      <div>
        <label>
          Owner
          <input name="owner" value={tx.owner} onChange={handleChange} />
        </label>
      </div>
      <div>
        <label>
          Account
          <input name="account" value={tx.account} onChange={handleChange} />
        </label>
      </div>
      <div>
        <label>
          Ticker
          <input name="ticker" value={tx.ticker ?? ""} onChange={handleChange} />
        </label>
      </div>
      <div>
        <label>
          Type
          <select name="type" value={tx.type ?? ""} onChange={handleChange}>
            <option value="buy">Buy</option>
            <option value="sell">Sell</option>
          </select>
        </label>
      </div>
      <div>
        <label>
          Date
          <input
            type="date"
            name="date"
            value={tx.date ?? ""}
            onChange={handleChange}
          />
        </label>
      </div>
      {errors.length > 0 && (
        <div style={{ color: "red" }}>
          <ul>
            {errors.map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
        </div>
      )}
      {status && <div>{status}</div>}
      <button type="submit">Submit Trade</button>
    </form>
  );
}
