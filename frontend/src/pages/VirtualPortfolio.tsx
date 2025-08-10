import { useEffect, useState } from "react";
import {
  getVirtualPortfolios,
  getVirtualPortfolio,
  createVirtualPortfolio,
  updateVirtualPortfolio,
  deleteVirtualPortfolio,
} from "../api";
import type { VirtualHolding, VirtualPortfolio as VP } from "../types";

export function VirtualPortfolio() {
  const [portfolios, setPortfolios] = useState<VP[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [id, setId] = useState("");
  const [name, setName] = useState("");
  const [holdings, setHoldings] = useState<VirtualHolding[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getVirtualPortfolios()
      .then(setPortfolios)
      .catch((e) => setError(String(e)));
  }, []);

  async function load(id: string) {
    try {
      const vp = await getVirtualPortfolio(id);
      setSelected(id);
      setId(vp.id);
      setName(vp.name);
      setHoldings(vp.holdings || []);
    } catch (e) {
      setError(String(e));
    }
  }

  function updateHolding(
    idx: number,
    field: keyof VirtualHolding,
    value: string | number | undefined,
  ) {
    setHoldings((prev) =>
      prev.map((h, i) => (i === idx ? { ...h, [field]: value } : h)),
    );
  }

  function addHolding() {
    setHoldings((prev) => [...prev, { ticker: "", units: 0 }]);
  }

  function removeHolding(idx: number) {
    setHoldings((prev) => prev.filter((_, i) => i !== idx));
  }

  async function handleSave() {
    setMessage(null);
    setError(null);
    const payload: VP = { id, name, holdings };
    try {
      if (selected != null) {
        await updateVirtualPortfolio(payload);
      } else {
        const created = await createVirtualPortfolio(payload);
        setSelected(created.id);
        setId(created.id);
      }
      setMessage("Saved");
      setPortfolios(await getVirtualPortfolios());
    } catch (e) {
      setError(String(e));
    }
  }

  async function handleDelete() {
    if (selected == null) return;
    try {
      await deleteVirtualPortfolio(selected);
      setSelected(null);
      setId("");
      setName("");
      setHoldings([]);
      setPortfolios(await getVirtualPortfolios());
    } catch (e) {
      setError(String(e));
    }
  }

  return (
    <div>
      <h1>Virtual Portfolios</h1>

      {error && <p style={{ color: "red" }}>{error}</p>}
      {message && <p style={{ color: "green" }}>{message}</p>}

        <div style={{ marginBottom: "1rem" }}>
          <label>
            Select
            <select
              value={selected ?? ""}
              onChange={(e) => {
                const val = e.target.value || null;
                if (val) {
                  load(val);
                } else {
                  setSelected(null);
                  setId("");
                  setName("");
                  setHoldings([]);
                }
              }}
              style={{ marginLeft: "0.5rem" }}
            >
              <option value="">New…</option>
              {portfolios.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div style={{ marginBottom: "1rem" }}>
          <label>
            ID
            <input
              type="text"
              value={id}
              onChange={(e) => setId(e.target.value)}
              style={{ marginLeft: "0.5rem" }}
              disabled={selected != null}
            />
          </label>
        </div>

        <div style={{ marginBottom: "1rem" }}>
          <label>
            Name
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              style={{ marginLeft: "0.5rem" }}
            />
          </label>
        </div>

        <div style={{ marginBottom: "1rem" }}>
          <h3>Holdings</h3>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <th>Ticker</th>
                <th>Units</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {holdings.map((h, i) => (
                <tr key={i}>
                  <td>
                    <input
                      value={h.ticker}
                      onChange={(e) => updateHolding(i, "ticker", e.target.value)}
                    />
                  </td>
                  <td>
                    <input
                      type="number"
                      value={h.units}
                      onChange={(e) =>
                        updateHolding(i, "units", parseFloat(e.target.value))
                      }
                    />
                  </td>
                  <td>
                    <button onClick={() => removeHolding(i)}>✕</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <button onClick={addHolding} style={{ marginTop: "0.5rem" }}>
            Add Holding
          </button>
        </div>

      <div style={{ marginTop: "1rem" }}>
        <button onClick={handleSave} style={{ marginRight: "0.5rem" }}>
          Save
        </button>
        {selected != null && (
          <button onClick={handleDelete} style={{ marginRight: "0.5rem" }}>
            Delete
          </button>
        )}
        <a href="/">Back</a>
      </div>
    </div>
  );
}

export default VirtualPortfolio;

