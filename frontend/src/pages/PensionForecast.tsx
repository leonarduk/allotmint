import { useEffect, useState } from "react";
import {
  LineChart,
  Line,
  ResponsiveContainer,
  XAxis,
  YAxis,
  Tooltip,
} from "recharts";
import { getOwners, getPensionForecast } from "../api";
import type { OwnerSummary } from "../types";
import { OwnerSelector } from "../components/OwnerSelector";
import { useTranslation } from "react-i18next";

export default function PensionForecast() {
  const [owners, setOwners] = useState<OwnerSummary[]>([]);
  const [owner, setOwner] = useState("");
  const [deathAge, setDeathAge] = useState(90);
  const [statePension, setStatePension] = useState<string>("");
  const [contribution, setContribution] = useState<string>("");
  const [desiredIncome, setDesiredIncome] = useState<string>("");
  const [data, setData] = useState<{ age: number; income: number }[]>([]);
  const [projectedPot, setProjectedPot] = useState<number | null>(null);
  const [pensionPot, setPensionPot] = useState<number | null>(null);
  const [currentAge, setCurrentAge] = useState<number | null>(null);
  const [retirementAge, setRetirementAge] = useState<number | null>(null);
  const [dob, setDob] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const { t } = useTranslation();

  useEffect(() => {
    getOwners()
      .then((os) => {
        setOwners(os);
        if (os.length > 0) {
          setOwner(os[0].owner);
        }
      })
      .catch(() => setOwners([]));
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await getPensionForecast({
        owner,
        deathAge,
        statePensionAnnual: statePension
          ? parseFloat(statePension)
          : undefined,
        contributionAnnual: contribution
          ? parseFloat(contribution)
          : undefined,
        desiredIncomeAnnual: desiredIncome
          ? parseFloat(desiredIncome)
          : undefined,
      });
      setData(res.forecast);
      setProjectedPot(res.projected_pot_gbp);
      setPensionPot(res.pension_pot_gbp);
      setCurrentAge(res.current_age);
      setRetirementAge(res.retirement_age);
      setDob(res.dob || null);
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
        <OwnerSelector owners={owners} selected={owner} onSelect={setOwner} />
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
      {currentAge !== null && dob && (
        <p className="mb-2">
          {t("pensionForecast.currentAge", { age: currentAge })} (
          {t("pensionForecast.birthDate", { dob })})
        </p>
      )}
      {retirementAge !== null && (
        <p className="mb-2">{t("pensionForecast.retirementAge", { age: retirementAge })}</p>
      )}
      {pensionPot !== null && (
        <p className="mb-2">
          {t("pensionForecast.pensionPot")}: £{pensionPot.toFixed(2)}
        </p>
      )}
      {projectedPot !== null && retirementAge !== null && (
        <p className="mb-2">
          Projected pot at {retirementAge}: £{projectedPot.toFixed(2)}
        </p>
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
