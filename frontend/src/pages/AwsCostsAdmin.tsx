import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { getAwsCosts, type AwsCostsResponse } from '../api';
import tableStyles from '../styles/table.module.css';

export default function AwsCostsAdmin() {
  const { t } = useTranslation();
  const [data, setData] = useState<AwsCostsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notAuthorized, setNotAuthorized] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const result = await getAwsCosts();
        if (cancelled) return;
        setData(result);
      } catch (e) {
        if (cancelled) return;
        if ((e as { status?: number })?.status === 403) {
          setNotAuthorized(true);
        } else {
          setError(e instanceof Error ? e.message : String(e));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (notAuthorized) {
    return (
      <div className="container mx-auto max-w-5xl p-4" role="alert">
        <p>{t('awsCostsAdmin.notAuthorized')}</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="container mx-auto max-w-5xl p-4" role="alert">
        <p className="text-red-600">{t('awsCostsAdmin.loadError')}</p>
        <p className="text-red-600">{error}</p>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="container mx-auto max-w-5xl p-4">
        <p>{t('common.loading')}</p>
      </div>
    );
  }

  if (!data || data.services.length === 0) {
    return (
      <div className="container mx-auto max-w-5xl p-4">
        <h2 className="mb-4 text-xl md:text-2xl">{t('awsCostsAdmin.title')}</h2>
        <p>{t('awsCostsAdmin.noData')}</p>
      </div>
    );
  }

  return (
    <div className="container mx-auto max-w-5xl p-4">
      <h2 className="mb-2 text-xl md:text-2xl">{t('awsCostsAdmin.title')}</h2>
      <p className="mb-4 text-sm opacity-70">
        {t('awsCostsAdmin.period', { start: data.start, end: data.end })}
      </p>
      <div className="overflow-x-auto">
        <table className={`${tableStyles.table} w-full`}>
          <thead>
            <tr>
              <th className={tableStyles.cell}>
                {t('awsCostsAdmin.columns.service')}
              </th>
              <th className={`${tableStyles.cell} ${tableStyles.right}`}>
                {t('awsCostsAdmin.columns.amount')}
              </th>
            </tr>
          </thead>
          <tbody>
            {data.services.map((row) => (
              <tr key={row.service}>
                <td className={tableStyles.cell}>{row.service}</td>
                <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                  {row.amount.toFixed(2)} {row.unit}
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <td className={tableStyles.cell}>
                <strong>{t('awsCostsAdmin.total')}</strong>
              </td>
              <td className={`${tableStyles.cell} ${tableStyles.right}`}>
                <strong>
                  {data.total.amount.toFixed(2)} {data.total.unit}
                </strong>
              </td>
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  );
}
