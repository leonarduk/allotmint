import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  getDataSyncStatus,
  startDataSync,
  type DataSyncDirection,
  type DataSyncRun,
  type DataSyncStatus,
} from '../api';
import SectionCard from './SectionCard';

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

function httpStatus(err: unknown): number | undefined {
  return (err as { status?: number } | null)?.status;
}

function RunSummary({
  label,
  run,
}: {
  label: string;
  run?: DataSyncRun | null;
}) {
  const { t } = useTranslation();
  if (!run) {
    return (
      <li>
        {label}: {t('support.dataSync.never', 'never run')}
      </li>
    );
  }
  const state = run.conclusion ?? run.status ?? '?';
  const when = run.created_at ? new Date(run.created_at).toLocaleString() : '';
  return (
    <li>
      {label}:{' '}
      {run.html_url ? (
        <a
          href={run.html_url}
          target="_blank"
          rel="noreferrer"
          className="underline"
        >
          {state}
        </a>
      ) : (
        state
      )}{' '}
      {when && (
        <span className="text-[var(--surface-muted-color)]">({when})</span>
      )}
    </li>
  );
}

/**
 * Pull the allotmint-data repo into the data bucket, or push the bucket back
 * to it as a pull request. Owner-only: renders nothing for anyone the backend
 * refuses (403).
 */
export default function DataSyncSection() {
  const { t } = useTranslation();
  const [allowed, setAllowed] = useState<boolean | null>(null);
  const [status, setStatus] = useState<DataSyncStatus | null>(null);
  const [busy, setBusy] = useState<DataSyncDirection | 'loading' | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [started, setStarted] = useState<DataSyncDirection | null>(null);

  const loadStatus = useCallback(async () => {
    setError(null);
    try {
      setStatus(await getDataSyncStatus());
      setAllowed(true);
    } catch (err) {
      const code = httpStatus(err);
      if (code === 403 || code === 404) {
        setAllowed(false);
        return;
      }
      setAllowed(true);
      setError(errorMessage(err));
    }
  }, []);

  useEffect(() => {
    void loadStatus();
  }, [loadStatus]);

  async function handleRefresh() {
    setBusy('loading');
    await loadStatus();
    setBusy(null);
  }

  async function handleSync(direction: DataSyncDirection) {
    if (
      direction === 'pull' &&
      !window.confirm(
        t(
          'support.dataSync.pullConfirm',
          'Replace the website data with the data in git? Website edits that have not been pushed and merged will be lost.'
        )
      )
    ) {
      return;
    }
    setBusy(direction);
    setError(null);
    setStarted(null);
    try {
      await startDataSync(direction);
      setStarted(direction);
      await loadStatus();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  if (!allowed) return null;

  const repo = status?.repo ?? 'allotmint-data';
  return (
    <SectionCard title={t('support.dataSync.title', 'Data sync with git')}>
      <p className="mb-2 text-sm text-[var(--surface-muted-color)]">
        {t(
          'support.dataSync.description',
          'Pull copies {{repo}} (main) into the website data; git wins. Push opens a pull request in {{repo}} with the website data.',
          { repo }
        )}
      </p>
      <p className="mb-2 text-sm text-orange-600">
        {t(
          'support.dataSync.pullWarning',
          'Pull discards website edits that have not been pushed and merged. Push and merge first if you want to keep them.'
        )}
      </p>
      {status && !status.configured && (
        <p className="mb-2 text-sm text-red-600">
          {t(
            'support.dataSync.notConfigured',
            'Data sync is not configured on this deployment. See docs/DEPLOY.md.'
          )}
        </p>
      )}
      {status?.configured && (
        <ul className="mb-2 text-sm">
          <RunSummary
            label={t('support.dataSync.lastPull', 'Last pull')}
            run={status.runs.pull}
          />
          <RunSummary
            label={t('support.dataSync.lastPush', 'Last push')}
            run={status.runs.push}
          />
        </ul>
      )}
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => handleSync('pull')}
          disabled={busy !== null || !status?.configured}
          className="rounded bg-orange-600 px-4 py-2 text-white disabled:opacity-50"
        >
          {busy === 'pull'
            ? t('support.dataSync.starting', 'Starting...')
            : t('support.dataSync.pull', 'Pull from git')}
        </button>
        <button
          type="button"
          onClick={() => handleSync('push')}
          disabled={busy !== null || !status?.configured}
          className="rounded bg-blue-600 px-4 py-2 text-white disabled:opacity-50"
        >
          {busy === 'push'
            ? t('support.dataSync.starting', 'Starting...')
            : t('support.dataSync.push', 'Push to git (PR)')}
        </button>
        <button
          type="button"
          onClick={handleRefresh}
          disabled={busy !== null}
          className="rounded bg-[var(--surface-muted-bg)] px-4 py-2 disabled:opacity-50"
        >
          {t('support.dataSync.refresh', 'Refresh status')}
        </button>
      </div>
      {started && (
        <p className="mt-2 text-sm text-green-600" role="status">
          {started === 'pull'
            ? t(
                'support.dataSync.pullStarted',
                'Pull started. It takes a few minutes; reload the app once it succeeds.'
              )
            : t(
                'support.dataSync.pushStarted',
                'Push started. Review and merge the pull request it opens.'
              )}{' '}
          {started === 'push' && status?.pulls_url && (
            <a
              href={status.pulls_url}
              target="_blank"
              rel="noreferrer"
              className="underline"
            >
              {t('support.dataSync.openPulls', 'Open pull requests')}
            </a>
          )}
        </p>
      )}
      {error && (
        <p className="mt-2 text-sm text-red-600" role="alert">
          {error}
        </p>
      )}
    </SectionCard>
  );
}
