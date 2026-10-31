import { useState, type ChangeEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { importCostBasisCsv, type CostBasisImportResponse } from '../api';
import {
  buildCostBasisTemplateCsv,
  singleGapOwner,
  type CostBasisGap,
} from '../lib/costBasisChecklist';

type Props = {
  gaps: CostBasisGap[];
  /** Called after an import recorded a cost for at least one holding. */
  onImported?: () => void;
};

function downloadTemplate(gaps: CostBasisGap[]): void {
  const blob = new Blob([buildCostBasisTemplateCsv(gaps)], {
    type: 'text/csv;charset=utf-8',
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = 'purchase-prices.csv';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.setTimeout(() => URL.revokeObjectURL(url), 250);
}

/**
 * Bulk fill for the cost-basis checklist (#10095): download the gaps as a
 * purchase-price CSV, fill in date and unit cost, and upload it.
 */
export function CostBasisCsvImport({ gaps, onImported }: Props) {
  const { t } = useTranslation();
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<CostBasisImportResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const input = event.currentTarget;
    const file = input.files?.[0];
    if (!file) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const response = await importCostBasisCsv(file, singleGapOwner(gaps));
      setResult(response);
      if (response.updated.length > 0) onImported?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
      // Let the same file be chosen again after it is corrected.
      input.value = '';
    }
  };

  return (
    <div data-testid="cost-basis-csv-import" style={{ marginTop: '0.75rem' }}>
      <p style={{ fontSize: '0.85rem', color: 'var(--summary-card-label)' }}>
        {t('costBasisChecklist.importHelp')}
      </p>
      <button type="button" onClick={() => downloadTemplate(gaps)}>
        {t('costBasisChecklist.downloadTemplate')}
      </button>{' '}
      <label>
        {t('costBasisChecklist.uploadLabel')}{' '}
        <input
          type="file"
          accept=".csv,text/csv"
          disabled={busy}
          onChange={(event) => void handleFile(event)}
        />
      </label>
      {busy && <p role="status">{t('costBasisChecklist.importing')}</p>}
      {error && (
        <p role="alert">
          {t('costBasisChecklist.importFailed', { message: error })}
        </p>
      )}
      {result && (
        <div role="status">
          <p>
            {t('costBasisChecklist.importUpdated', {
              count: result.updated.length,
            })}{' '}
            {t('costBasisChecklist.importSkipped', {
              count: result.skipped.length,
            })}
          </p>
          {result.skipped.length > 0 && (
            <ul style={{ fontSize: '0.85rem' }}>
              {result.skipped.map((row) => (
                <li
                  key={`${row.line}-${row.account ?? ''}-${row.ticker ?? ''}`}
                >
                  {t('costBasisChecklist.importSkippedRow', {
                    line: row.line,
                    ticker: row.ticker ?? '—',
                    reason: row.skip_reason,
                  })}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

export default CostBasisCsvImport;
