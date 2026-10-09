import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { getAllowances } from "../api";
import AllowanceGuardianCard from "../components/AllowanceGuardianCard";
import EmptyState from "../components/EmptyState";
import TableSkeleton from "../components/skeletons/TableSkeleton";

interface AllowanceInfo {
  used: number;
  limit: number;
  remaining: number;
}

export default function AllowanceTracker() {
  const { t } = useTranslation();
  const [data, setData] = useState<Record<string, AllowanceInfo> | null>(null);
  const [owner, setOwner] = useState<string | null>(null);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getAllowances()
      .then((res) => {
        setData(res.allowances);
        setOwner(res.owner ?? null);
        setError(false);
      })
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <TableSkeleton rows={4} columns={3} label={t("app.loading")} />;
  if (error) return <p className="text-red-500">{t("allowanceTracker.loadFailed")}</p>;
  if (!data) return <EmptyState message={t("allowanceTracker.noData")} />;

  return (
    <div>
      <h1 className="mb-4 text-2xl md:text-4xl">{t("allowanceTracker.title")}</h1>
      <table className="min-w-full border-collapse border border-gray-300">
        <thead>
          <tr>
            <th className="border p-2 text-left">{t("allowanceTracker.account")}</th>
            <th className="border p-2 text-right">{t("allowanceTracker.used")}</th>
            <th className="border p-2 text-right">{t("allowanceTracker.available")}</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(data).map(([type, info]) => (
            <tr key={type}>
              <td className="border p-2 capitalize">{type}</td>
              <td className="border p-2 text-right">{info.used.toFixed(2)}</td>
              <td className="border p-2 text-right">{info.remaining.toFixed(2)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {owner && <AllowanceGuardianCard owner={owner} />}
    </div>
  );
}
