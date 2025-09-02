import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  listInstrumentMetadata,
  createInstrumentMetadata,
  updateInstrumentMetadata,
} from "../api";
import type { InstrumentMetadata } from "../types";

interface Row extends InstrumentMetadata {
  isNew?: boolean;
  _originalTicker?: string;
}

export default function InstrumentAdmin() {
  const { t } = useTranslation();
  const [rows, setRows] = useState<Row[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    listInstrumentMetadata()
      .then((data) =>
        setRows(data.map((r) => ({ ...r, _originalTicker: r.ticker }))),
      )
      .catch((e) => setError(String(e)));
  }, []);

  const handleChange = (
    index: number,
    field: keyof InstrumentMetadata,
    value: string,
  ) => {
    setRows((prev) => {
      const copy = [...prev];
      copy[index] = { ...copy[index], [field]: value };
      return copy;
    });
  };

  const handleAdd = () =>
    setRows((prev) => [
      ...prev,
      { ticker: "", name: "", region: "", sector: "", isNew: true },
    ]);

  const handleSave = async (row: Row) => {
    setMessage(null);
    if (!row.ticker) {
      setMessage(t("instrumentadmin.validation.ticker"));
      return;
    }
    if (!row.name) {
      setMessage(t("instrumentadmin.validation.name"));
      return;
    }
    try {
      if (row.isNew) {
        await createInstrumentMetadata(row);
      } else {
        await updateInstrumentMetadata(row._originalTicker ?? row.ticker, row);
      }
      setMessage(t("instrumentadmin.saveSuccess"));
      const fresh = await listInstrumentMetadata();
      setRows(fresh.map((r) => ({ ...r, _originalTicker: r.ticker })));
    } catch (e) {
      setMessage(t("instrumentadmin.saveError"));
    }
  };

  if (error) {
    return <p style={{ color: "red" }}>{error}</p>;
  }

  return (
    <div className="container mx-auto p-4 max-w-5xl">
      <h2 className="mb-4 text-xl md:text-2xl">
        {t("app.modes.instrumentadmin")}
      </h2>
      {message && <p>{message}</p>}
      <button
        type="button"
        onClick={handleAdd}
        style={{ marginBottom: "0.5rem" }}
      >
        {t("instrumentadmin.add")}
      </button>
      <table className="w-full border-collapse">
        <thead>
          <tr>
            <th>{t("instrumentadmin.ticker")}</th>
            <th>{t("instrumentadmin.name")}</th>
            <th>{t("instrumentadmin.region")}</th>
            <th>{t("instrumentadmin.sector")}</th>
            <th>{t("instrumentadmin.actions")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, idx) => (
            <tr key={r._originalTicker ?? idx}>
              <td>
                <input
                  value={r.ticker}
                  onChange={(e) => handleChange(idx, "ticker", e.target.value)}
                />
              </td>
              <td>
                <input
                  value={r.name}
                  onChange={(e) => handleChange(idx, "name", e.target.value)}
                />
              </td>
              <td>
                <input
                  value={r.region ?? ""}
                  onChange={(e) => handleChange(idx, "region", e.target.value)}
                />
              </td>
              <td>
                <input
                  value={r.sector ?? ""}
                  onChange={(e) => handleChange(idx, "sector", e.target.value)}
                />
              </td>
              <td>
                <button type="button" onClick={() => handleSave(r)}>
                  {t("instrumentadmin.save")}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

