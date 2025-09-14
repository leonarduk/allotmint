import { useEffect, useState } from "react";
import { getAllowances } from "../api";
import EmptyState from "../components/EmptyState";

interface AllowanceInfo {
  used: number;
  limit: number;
  remaining: number;
}

export default function TaxAllowances() {
  const [data, setData] = useState<Record<string, AllowanceInfo> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getAllowances()
      .then((res) => {
        setData(res.allowances);
        setError(null);
      })
      .catch(() => setError("Failed to load allowances"))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <p>Loading...</p>;
  if (error) return <p className="text-red-500">{error}</p>;
  if (!data) return <EmptyState message="No data" />;

  return (
    <div>
      <h1 className="mb-4 text-2xl md:text-4xl">Tax Allowances</h1>
      <table className="min-w-full border-collapse border border-gray-300">
        <thead>
          <tr>
            <th className="border p-2 text-left">Account</th>
            <th className="border p-2 text-right">Used</th>
            <th className="border p-2 text-right">Available</th>
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
    </div>
  );
}
