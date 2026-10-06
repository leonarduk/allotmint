import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  applyAppUpdate,
  getAppUpdateStatus,
  type AppUpdateResult,
  type AppUpdateStatus,
} from '../api';
import SectionCard from './SectionCard';

const shortSha = (sha: string | null | undefined) =>
  sha ? sha.slice(0, 7) : '?';

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

function httpStatus(err: unknown): number | undefined {
  return (err as { status?: number } | null)?.status;
}

function isNotFound(err: unknown): boolean {
  return httpStatus(err) === 404;
}

function StatusSummary({ status }: { status: AppUpdateStatus }) {
  const { t } = useTranslation();
  return (
    <div className="mb-2 text-sm">
      {status.branch && (
        <p>
          {t('support.appUpdate.branch', 'Branch')}:{' '}
          <code>{status.branch}</code>
          {status.upstream && (
            <>
              {' → '}
              <code>{status.upstream}</code>
            </>
          )}{' '}
          @ <code>{shortSha(status.current_commit)}</code>
        </p>
      )}
      {status.behind > 0 && (
        <p>
          {t('support.appUpdate.behind', '{{count}} new commit(s) available.', {
            count: status.behind,
          })}
        </p>
      )}
      {status.reason && <p className="text-gray-600">{status.reason}</p>}
    </div>
  );
}

function UpdateResult({ result }: { result: AppUpdateResult }) {
  const { t } = useTranslation();
  return (
    <div className="mt-3 space-y-1 text-sm" role="status">
      <p className="text-green-600">
        {t(
          'support.appUpdate.updated',
          'Updated {{from}} → {{to}} ({{count}} file(s) changed).',
          {
            from: shortSha(result.previous_commit),
            to: shortSha(result.current_commit),
            count: result.changed_files.length,
          }
        )}
      </p>
      {result.dependencies_changed.length > 0 && (
        <p className="text-orange-600">
          {t(
            'support.appUpdate.dependencies',
            'Dependencies changed ({{files}}): re-run pip install / npm install and restart the app.',
            { files: result.dependencies_changed.join(', ') }
          )}
        </p>
      )}
      {result.backend_changed && (
        <p>
          {t(
            'support.appUpdate.backendRestart',
            'Backend code changed. It restarts automatically when run with reload enabled (the default for the local run scripts); otherwise restart it.'
          )}
        </p>
      )}
      <button
        type="button"
        onClick={() => window.location.reload()}
        className="rounded bg-gray-200 px-2 py-1"
      >
        {t('support.appUpdate.reload', 'Reload page')}
      </button>
    </div>
  );
}

/**
 * Pull the latest code into a local git checkout (fast-forward only).
 *
 * Renders nothing when the backend does not expose the update route, which is
 * the case for every non-local deployment (AWS): there the app is updated by
 * the deploy pipeline, not from inside the running app.
 */
export default function AppUpdateSection() {
  const { t } = useTranslation();
  const [supported, setSupported] = useState<boolean | null>(null);
  const [status, setStatus] = useState<AppUpdateStatus | null>(null);
  const [busy, setBusy] = useState<'checking' | 'updating' | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AppUpdateResult | null>(null);

  const loadStatus = useCallback(async (fetchRemote: boolean) => {
    setError(null);
    try {
      setStatus(await getAppUpdateStatus(fetchRemote));
      setSupported(true);
    } catch (err) {
      if (isNotFound(err)) {
        setSupported(false);
        return;
      }
      setSupported(true);
      setError(errorMessage(err));
    }
  }, []);

  useEffect(() => {
    // Initial load skips `git fetch` so opening the Support page stays cheap
    // and offline-safe; "Check for updates" does the network round trip.
    void loadStatus(false);
  }, [loadStatus]);

  async function handleCheck() {
    setBusy('checking');
    setResult(null);
    await loadStatus(true);
    setBusy(null);
  }

  async function handleUpdate() {
    setBusy('updating');
    setError(null);
    try {
      setResult(await applyAppUpdate());
      await loadStatus(false);
    } catch (err) {
      // No HTTP status means the response never arrived. The update touches
      // backend/, so uvicorn --reload may have restarted the worker before
      // replying even though the fast-forward succeeded.
      setError(
        httpStatus(err) === undefined
          ? t(
              'support.appUpdate.noResponse',
              'No response from the backend ({{error}}). It may have restarted after updating; use Check for updates to confirm.',
              { error: errorMessage(err) }
            )
          : errorMessage(err)
      );
    } finally {
      setBusy(null);
    }
  }

  if (!supported) return null;

  return (
    <SectionCard title={t('support.appUpdate.title', 'Update app')}>
      <p className="mb-2 text-sm text-gray-600">
        {t(
          'support.appUpdate.description',
          'Fast-forward this local checkout to the latest commit on its upstream branch. Only available for local deployments.'
        )}
      </p>
      {status && <StatusSummary status={status} />}
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={handleCheck}
          disabled={busy !== null}
          className="rounded bg-blue-600 px-4 py-2 text-white disabled:opacity-50"
        >
          {busy === 'checking'
            ? t('support.appUpdate.checking', 'Checking...')
            : t('support.appUpdate.check', 'Check for updates')}
        </button>
        <button
          type="button"
          onClick={handleUpdate}
          disabled={busy !== null || !status?.can_update}
          className="rounded bg-green-600 px-4 py-2 text-white disabled:opacity-50"
        >
          {busy === 'updating'
            ? t('support.appUpdate.updating', 'Updating...')
            : t('support.appUpdate.update', 'Update now')}
        </button>
      </div>
      {error && (
        <p className="mt-2 text-sm text-red-600" role="alert">
          {error}
        </p>
      )}
      {result && <UpdateResult result={result} />}
    </SectionCard>
  );
}
