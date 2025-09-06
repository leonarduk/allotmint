import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  listInstrumentMetadata,
  createInstrumentMetadata,
  updateInstrumentMetadata,
} from "../api";
import { useFilterableTable, type Filter } from "../hooks/useFilterableTable";

interface Row {
  ticker: string;
  exchange: string;
  name: string;
  region?: string | null;
  sector?: string | null;
  isNew?: boolean;
  _originalTicker?: string;
  _originalExchange?: string;
}

export default function InstrumentAdmin() {
  const { t } = useTranslation();
  const [rows, setRows] = useState<Row[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const {
    rows: filteredRows,
    setFilter,
    filters,
  } = useFilterableTable<Row, { search: Filter<Row, unknown> }>(rows, "ticker", {
    search: {
      value: "" as unknown,
      predicate: (row, value) => {
        if (!value) return true;
        const q = String(value).toLowerCase();
        return [row.ticker, row.exchange, row.name, row.region ?? "", row.sector ?? ""]
          .some((field) => field.toLowerCase().includes(q));
      },
    },
  });

  useEffect(() => {
    listInstrumentMetadata()
      .then((data) =>
        setRows(
          data.map((r: any) => {
            const [sym, exch] = String(r.ticker ?? "").split(".");
            const exchange = r.exchange ?? exch ?? "";
            return {
              ticker: sym ?? "",
              exchange,
              name: r.name ?? "",
              region: r.region ?? "",
              sector: r.sector ?? "",
              _originalTicker: sym ?? "",
              _originalExchange: exchange,
            } as Row;
          }),
        ),
      )
      .catch((e) => setError(String(e)));
  }, []);

  const handleChange = (row: Row, field: keyof Row, value: string) => {
    setRows((prev) => {
      const index = prev.indexOf(row);
      if (index === -1) return prev;
      const copy = [...prev];
      copy[index] = { ...copy[index], [field]: value };
      return copy;
    });
  };

  const handleAdd = () =>
    setRows((prev) => [
      ...prev,
      { ticker: "", exchange: "", name: "", region: "", sector: "", isNew: true },
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
      const payload = {
        ticker: `${row.ticker}.${row.exchange}`,
        exchange: row.exchange,
        name: row.name,
        region: row.region,
        sector: row.sector,
      };
      if (row.isNew) {
        await createInstrumentMetadata(row.ticker, row.exchange, payload);
      } else {
        await updateInstrumentMetadata(row.ticker, row.exchange, payload);
      }
      setMessage(t("instrumentadmin.saveSuccess"));
      const fresh = await listInstrumentMetadata();
      setRows(
        fresh.map((r: any) => {
          const [sym, exch] = String(r.ticker ?? "").split(".");
          const exchange = r.exchange ?? exch ?? "";
          return {
            ticker: sym ?? "",
            exchange,
            name: r.name ?? "",
            region: r.region ?? "",
            sector: r.sector ?? "",
            _originalTicker: sym ?? "",
            _originalExchange: exchange,
          } as Row;
        }),
      );
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
      <input
        type="text"
        placeholder={t("instrumentadmin.searchPlaceholder")}
        value={String((filters as any).search ?? "")}
        onChange={(e) => setFilter("search", e.target.value)}
        style={{ marginBottom: "0.5rem", display: "block" }}
      />
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
            <th>{t("instrumentadmin.exchange")}</th>
            <th>{t("instrumentadmin.name")}</th>
            <th>{t("instrumentadmin.region")}</th>
            <th>{t("instrumentadmin.sector")}</th>
            <th>{t("instrumentadmin.actions")}</th>
          </tr>
        </thead>
        <tbody>
          {filteredRows.map((r, idx) => (
            <tr key={r._originalTicker ?? idx}>
              <td>
                <input
                  value={r.ticker}
                  onChange={(e) => handleChange(r, "ticker", e.target.value)}
                />
              </td>
              <td>
                <input
                  value={r.exchange}
                  onChange={(e) => handleChange(r, "exchange", e.target.value)}
                />
              </td>
              <td>
                <input
                  value={r.name}
                  onChange={(e) => handleChange(r, "name", e.target.value)}
                />
              </td>
              <td>
                <input
                  value={r.region ?? ""}
                  onChange={(e) => handleChange(r, "region", e.target.value)}
                />
              </td>
              <td>
                <input
                  value={r.sector ?? ""}
                  onChange={(e) => handleChange(r, "sector", e.target.value)}
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
