import { Fragment, useEffect, useState } from "react";
import { getEvents, runScenario } from "../api";
import type { ScenarioEvent, ScenarioResult } from "../types";

const HORIZONS = ["1d", "1w", "1m", "3m", "1y"];

export default function ScenarioTester() {
  const [events, setEvents] = useState<ScenarioEvent[]>([]);
  const [eventId, setEventId] = useState("");
  const [horizons, setHorizons] = useState<string[]>([]);
  const [results, setResults] = useState<ScenarioResult[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fmt = new Intl.NumberFormat("en-GB", {
    style: "currency",
    currency: "GBP",
  });

  useEffect(() => {
    getEvents()
      .then(setEvents)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  const toggleHorizon = (h: string) => {
    setHorizons((prev) =>
      prev.includes(h) ? prev.filter((x) => x !== h) : [...prev, h],
    );
  };

  const canRun = eventId !== "" && horizons.length > 0;

  async function handleRun() {
    setError(null);
    try {
      const data = await runScenario(eventId, horizons);
      setResults(data);
    } catch (e) {
      setResults(null);
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="container mx-auto p-4">
      <div className="mb-4 flex flex-col gap-2 md:flex-row">
        <select
          value={eventId}
          onChange={(e) => setEventId(e.target.value)}
          className="md:mr-2"
        >
          <option value="">Select Event</option>
          {events.map((ev) => (
            <option key={ev.id} value={ev.id}>
              {ev.name}
            </option>
          ))}
        </select>
        <div className="flex flex-wrap items-center gap-2 md:mr-2">
          {HORIZONS.map((h) => (
            <label key={h} className="flex items-center gap-1">
              <input
                type="checkbox"
                checked={horizons.includes(h)}
                onChange={() => toggleHorizon(h)}
              />
              {h}
            </label>
          ))}
        </div>
        <button onClick={handleRun} disabled={!canRun}>
          Apply
        </button>
      </div>
      {error && <div className="text-red-500">{error}</div>}
      {results && (
        <div className="overflow-auto">
          <table className="min-w-full border">
            <thead>
              <tr className="bg-gray-100">
                <th className="p-2 text-left">Owner</th>
                {horizons.flatMap((h) => [
                  <th key={`${h}-b`} className="p-2 text-right">
                    {h} Baseline (£)
                  </th>,
                  <th key={`${h}-s`} className="p-2 text-right">
                    {h} Shocked (£)
                  </th>,
                  <th key={`${h}-p`} className="p-2 text-right">
                    {h} % Impact
                  </th>,
                ])}
              </tr>
            </thead>
            <tbody>
              {results.map((r, i) => (
                <tr key={i} className="border-t">
                  <td className="p-2">{r.owner}</td>
                  {horizons.map((h) => {
                    const data = r.horizons[h];
                    const baseline = data?.baseline ?? null;
                    const shocked = data?.shocked ?? null;
                    const pct =
                      baseline != null && shocked != null
                        ? ((shocked - baseline) / baseline) * 100.0
                        : null;
                    return (
                      <Fragment key={h}>
                        <td className="p-2 text-right">
                          {baseline != null ? fmt.format(baseline) : "—"}
                        </td>
                        <td className="p-2 text-right">
                          {shocked != null ? fmt.format(shocked) : "—"}
                        </td>
                        <td className="p-2 text-right">
                          {pct != null ? pct.toFixed(2) + "%" : "—"}
                        </td>
                      </Fragment>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

