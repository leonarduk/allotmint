import { useEffect, useState } from "react";
import {
  getVirtualPortfolios,
  getVirtualPortfolio,
  createVirtualPortfolio,
  updateVirtualPortfolio,
  deleteVirtualPortfolio,
  getOwners,
} from "../api";
import type {
  SyntheticHolding,
  VirtualPortfolio as VP,
  OwnerSummary,
} from "../types";

export function VirtualPortfolio() {
  const [portfolios, setPortfolios] = useState<VP[]>([]);
  const [owners, setOwners] = useState<OwnerSummary[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [name, setName] = useState("");
  const [accounts, setAccounts] = useState<string[]>([]);
  const [holdings, setHoldings] = useState<SyntheticHolding[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getVirtualPortfolios()
      .then(setPortfolios)
      .catch((e) => setError(String(e)));
    getOwners().then(setOwners).catch((e) => setError(String(e)));
  }, []);

  async function load(id: number) {
    try {
      const vp = await getVirtualPortfolio(id);
      setSelected(id);
      setName(vp.name);
      setAccounts(vp.accounts);
      setHoldings(vp.holdings || []);
    } catch (e) {
      setError(String(e));
    }
  }

  function toggleAccount(account: string) {
    setAccounts((prev) =>
      prev.includes(account)
        ? prev.filter((a) => a !== account)
        : [...prev, account],
    );
  }

  function updateHolding(
    idx: number,
    field: keyof SyntheticHolding,
    value: string | number | undefined,
  ) {
    setHoldings((prev) =>
      prev.map((h, i) => (i === idx ? { ...h, [field]: value } : h)),
    );
  }

  function addHolding() {
    setHoldings((prev) => [...prev, { ticker: "", units: 0, price: undefined, purchase_date: "" }]);
  }

  function removeHolding(idx: number) {
    setHoldings((prev) => prev.filter((_, i) => i !== idx));
  }

  async function handleSave() {
    setMessage(null);
    setError(null);
    const payload: VP = { name, accounts, holdings };
    try {
      if (selected != null) {
        await updateVirtualPortfolio(selected, payload);
      } else {
        const created = await createVirtualPortfolio(payload);
        setSelected(created.id ?? null);
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
      setName("");
      setAccounts([]);
      setHoldings([]);
      setPortfolios(await getVirtualPortfolios());
    } catch (e) {
      setError(String(e));
    }
  }

  return (
    <div className="container mx-auto p-4">
      <h1 className="mb-4 text-2xl md:text-4xl">Virtual Portfolios</h1>

      {error && <p className="text-red-500">{error}</p>}
      {message && <p className="text-green-600">{message}</p>}

      <div className="mb-4">
        <label>
          Select
          <select
            value={selected ?? ""}
            onChange={(e) => {
              const id = e.target.value ? Number(e.target.value) : null;
              if (id) load(id);
            }}
            className="ml-2"
          >
            <option value="">New…</option>
            {portfolios.map((p) => (
              <option key={p.id} value={p.id ?? ""}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="mb-4">
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

      <fieldset className="mb-4">
        <legend>Include Accounts</legend>
        {owners.map((o) => (
          <div key={o.owner} style={{ marginBottom: "0.25rem" }}>
            <strong>{o.owner}</strong>
            {o.accounts.map((a) => {
              const val = `${o.owner}:${a}`;
              return (
                <label key={val} style={{ marginLeft: "0.5rem" }}>
                  <input
                    type="checkbox"
                    checked={accounts.includes(val)}
                    onChange={() => toggleAccount(val)}
                  />
                  {a}
                </label>
              );
            })}
          </div>
        ))}
      </fieldset>

      <div className="mb-4">
        <h3>Synthetic Holdings</h3>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <th>Ticker</th>
              <th>Units</th>
              <th>Price</th>
              <th>Date</th>
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
                  <input
                    type="number"
                    value={h.price ?? ""}
                    onChange={(e) =>
                      updateHolding(i, "price", parseFloat(e.target.value))
                    }
                  />
                </td>
                <td>
                  <input
                    type="date"
                    value={h.purchase_date ?? ""}
                    onChange={(e) =>
                      updateHolding(i, "purchase_date", e.target.value)
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

      <div className="mt-4">
        <button onClick={handleSave} className="mr-2">
          Save
        </button>
        {selected != null && (
          <button onClick={handleDelete} className="mr-2">
            Delete
          </button>
        )}
        <a href="/">Back</a>
      </div>
    </div>
  );
}

export default VirtualPortfolio;

