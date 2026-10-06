import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { API_BASE, fetchJson } from '../api';

const endpoints = ['/health', '/owners', '/groups'];

interface Result {
  path: string;
  ok: boolean;
  status?: number;
}

export default function SmokeTest() {
  const { t } = useTranslation();
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
      <h1>{t('smokeTest.title')}</h1>
      <ul aria-label={t('smokeTest.results')}>
        {results.map((r) => (
          <li key={r.path} style={{ color: r.ok ? 'green' : 'red' }}>
            {r.path}: {r.ok ? t('smokeTest.ok') : t('smokeTest.failed')}{' '}
            {r.status !== undefined && `(${r.status})`}
          </li>
        ))}
      </ul>
    </div>
  );
}
