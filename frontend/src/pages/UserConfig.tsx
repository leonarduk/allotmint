import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  getOwners,
  getUserConfig,
  updateUserConfig,
  getApprovals,
  addApproval,
  removeApproval,
} from "../api";
import type { Approval, OwnerSummary, UserConfig } from "../types";

export default function UserConfigPage() {
  const { t } = useTranslation();
  const [owners, setOwners] = useState<OwnerSummary[]>([]);
  const [owner, setOwner] = useState("");
  const [cfg, setCfg] = useState<UserConfig>({});
  const [status, setStatus] = useState<string | null>(null);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [newTicker, setNewTicker] = useState("");
  const [newDate, setNewDate] = useState("");
  const [approvalsError, setApprovalsError] = useState<string | null>(null);

  useEffect(() => {
    getOwners().then(setOwners).catch(() => {
      /* ignore */
    });
  }, []);

  useEffect(() => {
    if (owner) {
      getUserConfig(owner)
        .then((res) => {
          setCfg({
            ...res,
            approval_exempt_tickers: Array.isArray(res.approval_exempt_tickers)
              ? res.approval_exempt_tickers
              : [],
            approval_exempt_types: Array.isArray(res.approval_exempt_types)
              ? res.approval_exempt_types
              : [],
          });
        })
        .catch(() => {
          setCfg({});
        });
      getApprovals(owner)
        .then((res) => {
          setApprovals(res.approvals);
          setApprovalsError(null);
        })
        .catch(() => {
          setApprovals([]);
          setApprovalsError("Failed to load approvals");
        });
    }
  }, [owner]);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!owner) return;
    setStatus("saving");
    try {
      await updateUserConfig(owner, cfg);
      setStatus("saved");
    } catch {
      setStatus("error");
    }
  }

  async function add(e: React.FormEvent) {
    e.preventDefault();
    if (!owner || !newTicker || !newDate) return;
    try {
      const res = await addApproval(owner, newTicker, newDate);
      setApprovals(res.approvals);
      setNewTicker("");
      setNewDate("");
      setApprovalsError(null);
    } catch {
      setApprovalsError("Failed to add approval");
    }
  }

  async function remove(ticker: string) {
    if (!owner) return;
    try {
      const res = await removeApproval(owner, ticker);
      setApprovals(res.approvals);
      setApprovalsError(null);
    } catch {
      setApprovalsError("Failed to remove approval");
    }
  }

  return (
    <div className="container mx-auto max-w-xl space-y-4 p-4">
      <h1 className="text-2xl md:text-4xl">{t("userConfig.title", "User Settings")}</h1>
      <select
        className="w-full border p-2"
        value={owner}
        onChange={(e) => setOwner(e.target.value)}
      >
        <option value="">{t("userConfig.selectOwner", "Select owner")}</option>
        {owners.map((o) => (
          <option key={o.owner} value={o.owner}>
            {o.owner}
          </option>
        ))}
      </select>
      {owner && (
        <>
          <form onSubmit={save} className="space-y-2">
            <div>
              <label className="block text-sm">
                {t("userConfig.holdDays", "Min Hold Days")}
              </label>
              <input
                type="number"
                className="w-full border p-1"
                value={cfg.hold_days_min ?? ""}
                onChange={(e) =>
                  setCfg({
                    ...cfg,
                    hold_days_min: e.target.value ? Number(e.target.value) : undefined,
                  })
                }
              />
            </div>
            <div>
              <label className="block text-sm">
                {t("userConfig.maxTrades", "Max Trades / Month")}
              </label>
              <input
                type="number"
                className="w-full border p-1"
                value={cfg.max_trades_per_month ?? ""}
                onChange={(e) =>
                  setCfg({
                    ...cfg,
                    max_trades_per_month: e.target.value
                      ? Number(e.target.value)
                      : undefined,
                  })
                }
              />
            </div>
            <div>
              <label className="block text-sm">
                {t("userConfig.exemptTickers", "Approval Exempt Tickers")}
              </label>
              <input
                type="text"
                className="w-full border p-1"
                value={(
                  Array.isArray(cfg.approval_exempt_tickers)
                    ? cfg.approval_exempt_tickers
                    : []
                ).join(",")}
                onChange={(e) =>
                  setCfg({
                    ...cfg,
                    approval_exempt_tickers: e.target.value
                      ? e.target.value.split(/,\s*/)
                      : [],
                  })
                }
              />
            </div>
            <div>
              <label className="block text-sm">
                {t("userConfig.exemptTypes", "Approval Exempt Types")}
              </label>
              <input
                type="text"
                className="w-full border p-1"
                value={(
                  Array.isArray(cfg.approval_exempt_types)
                    ? cfg.approval_exempt_types
                    : []
                ).join(",")}
                onChange={(e) =>
                  setCfg({
                    ...cfg,
                    approval_exempt_types: e.target.value
                      ? e.target.value.split(/,\s*/)
                      : [],
                  })
                }
              />
            </div>
            <button
              type="submit"
              className="bg-blue-500 px-4 py-2 text-white"
              disabled={status === "saving"}
            >
              {status === "saving"
                ? t("userConfig.saving", "Saving...")
                : t("userConfig.save", "Save")}
            </button>
            {status === "saved" && <span>{t("userConfig.saved", "Saved")}</span>}
            {status === "error" && (
              <span className="text-red-500">{t("userConfig.error", "Error")}</span>
            )}
          </form>
          <div className="space-y-2 pt-4">
            <h2 className="text-xl">
              {t("userConfig.approvals", "Approvals")}
            </h2>
            <table className="w-full border">
              <thead>
                <tr>
                  <th className="border px-2 text-left">Ticker</th>
                  <th className="border px-2 text-left">Date</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {approvals.map((a) => (
                  <tr key={a.ticker}>
                    <td className="border px-2">{a.ticker}</td>
                    <td className="border px-2">{a.approved_on}</td>
                    <td className="border px-2 text-right">
                      <button
                        type="button"
                        className="text-red-500"
                        onClick={() => remove(a.ticker)}
                      >
                        {t("userConfig.remove", "Remove")}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {approvalsError && (
              <div className="text-red-500">{approvalsError}</div>
            )}
            <form onSubmit={add} className="flex space-x-2">
              <input
                type="text"
                className="flex-1 border p-1"
                placeholder="Ticker"
                value={newTicker}
                onChange={(e) => setNewTicker(e.target.value)}
              />
              <input
                type="date"
                className="border p-1"
                value={newDate}
                onChange={(e) => setNewDate(e.target.value)}
              />
              <button type="submit" className="bg-blue-500 px-2 text-white">
                {t("userConfig.add", "Add")}
              </button>
            </form>
          </div>
        </>
      )}
    </div>
  );
}
