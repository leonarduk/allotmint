import { useState } from "react";
import {
  LineChart,
  Line,
  ResponsiveContainer,
  XAxis,
  YAxis,
  Tooltip,
} from "recharts";
import { getPensionForecast } from "../api";

export default function PensionForecast() {
  const [dob, setDob] = useState("");
  const [retirementAge, setRetirementAge] = useState(65);
  const [deathAge, setDeathAge] = useState(90);
  const [statePension, setStatePension] = useState<string>("");
  const [contribution, setContribution] = useState<string>("");
  const [desiredIncome, setDesiredIncome] = useState<string>("");
  const [data, setData] = useState<{ age: number; income: number }[]>([]);
  const [projectedPot, setProjectedPot] = useState<number | null>(null);
  const [earliestAge, setEarliestAge] = useState<number | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await getPensionForecast(
        dob,
        retirementAge,
        deathAge,
        statePension ? parseFloat(statePension) : undefined,
        contribution ? parseFloat(contribution) : undefined,
        desiredIncome ? parseFloat(desiredIncome) : undefined,
      );
      setData(res.forecast);
      setProjectedPot(res.projected_pot_gbp);
      setEarliestAge(res.earliest_retirement_age);
      setErr(null);
    } catch (ex: any) {
      setErr(String(ex));
      setData([]);
    }
  };

  return (
    <div>
      <h1 className="mb-4 text-2xl md:text-4xl">Pension Forecast</h1>
      <form onSubmit={handleSubmit} className="mb-4 space-y-2">
        <div>
          <label className="mr-2">DOB:</label>
          <input
            type="date"
            value={dob}
            onChange={(e) => setDob(e.target.value)}
            required
          />
        </div>
        <div>
          <label className="mr-2">Retirement Age:</label>
          <input
            type="number"
            value={retirementAge}
            onChange={(e) => setRetirementAge(Number(e.target.value))}
            required
          />
        </div>
        <div>
          <label className="mr-2">Death Age:</label>
          <input
            type="number"
            value={deathAge}
            onChange={(e) => setDeathAge(Number(e.target.value))}
            required
          />
        </div>
        <div>
          <label className="mr-2">State Pension (£/yr):</label>
          <input
            type="number"
            value={statePension}
            onChange={(e) => setStatePension(e.target.value)}
          />
        </div>
        <div>
          <label className="mr-2">Annual Contribution (£):</label>
          <input
            type="number"
            value={contribution}
            onChange={(e) => setContribution(e.target.value)}
          />
        </div>
        <div>
          <label className="mr-2">Desired Income (£/yr):</label>
          <input
            type="number"
            value={desiredIncome}
            onChange={(e) => setDesiredIncome(e.target.value)}
          />
        </div>
        <button type="submit" className="mt-2 rounded bg-blue-500 px-4 py-2 text-white">
          Forecast
        </button>
      </form>
      {err && <p className="text-red-500">{err}</p>}
      {projectedPot !== null && (
        <p className="mb-2">Projected pot at {retirementAge}: £{projectedPot.toFixed(2)}</p>
      )}
      {earliestAge !== null && (
        <p className="mb-2">Earliest feasible retirement age: {earliestAge}</p>
      )}
      {data.length > 0 && (
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={data}>
            <XAxis dataKey="age" />
            <YAxis />
            <Tooltip />
            <Line type="monotone" dataKey="income" stroke="#8884d8" dot={false} />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
