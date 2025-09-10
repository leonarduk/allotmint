import { useEffect, useState } from 'react';
import { API_BASE, fetchJson } from '../api';

const endpoints = ['/health', '/owners', '/groups'];

interface Result {
  path: string;
  ok: boolean;
  status?: number;
}

export default function SmokeTest() {
  const [results, setResults] = useState<Result[]>([]);

  useEffect(() => {
    const run = async () => {
      const res = await Promise.all(
        endpoints.map(async (path) => {
          try {
            await fetchJson(`${API_BASE}${path}`);
            return { path, ok: true, status: 200 };
          } catch (err: any) {
            return { path, ok: false, status: err?.status };
          }
        })
      );
      setResults(res);
    };
    run();
  }, []);

  return (
    <div style={{ padding: '1rem' }}>
      <h1>Smoke test</h1>
      <ul>
        {results.map((r) => (
          <li key={r.path} style={{ color: r.ok ? 'green' : 'red' }}>
            {r.path}: {r.ok ? 'ok' : 'failed'}{' '}
            {r.status !== undefined && `(${r.status})`}
          </li>
        ))}
      </ul>
    </div>
  );
}
