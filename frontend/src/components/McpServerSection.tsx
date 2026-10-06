import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  getMcpServerStatus,
  restartMcpServer,
  type McpServerRestartResult,
  type McpServerStatus,
} from '../api';

const shortSha = (sha: string | null | undefined) =>
  sha ? sha.slice(0, 7) : '?';

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

function isNotFound(err: unknown): boolean {
  return (err as { status?: number } | null)?.status === 404;
}

function StatusSummary({ status }: { status: McpServerStatus }) {
  const { t } = useTranslation();
  return (
    <div className="mb-2 space-y-1 text-sm">
      <p>
        {status.running
          ? t(
              'support.mcpServer.running',
              'Running on port {{port}} (pid {{pid}}, started {{started}}).',
              {
                port: status.port,
                pid: status.pid,
                started: status.started_at
                  ? new Date(status.started_at).toLocaleString()
                  : '?',
              }
            )
          : t('support.mcpServer.stopped', 'Not running on port {{port}}.', {
              port: status.port ?? '?',
            })}
      </p>
      {status.pro_dir && (
        <p>
          allotmint-pro:{' '}
          <code title={status.pro_dir}>{shortSha(status.pro_commit)}</code>
        </p>
      )}
      {status.tool_count !== null && (
        <p>
          {t('support.mcpServer.toolCount', '{{count}} tool(s) listed.', {
            count: status.tool_count,
          })}
        </p>
      )}
      {status.tools_error && (
        <p className="text-amber-600">{status.tools_error}</p>
      )}
      {status.code_changed && (
        <div className="text-amber-600" role="status">
          <p>
            {t(
              'support.mcpServer.codeChanged',
              'Code changed since the server started; restart it to pick the changes up.'
            )}
          </p>
          <ul className="ml-4 list-disc">
            {status.code_changes.map((change) => (
              <li key={change}>{change}</li>
            ))}
          </ul>
        </div>
      )}
      {status.reason && <p className="text-gray-600">{status.reason}</p>}
    </div>
  );
}

function RestartConfirmation({
  status,
  onConfirm,
  onCancel,
}: {
  status: McpServerStatus;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const { t } = useTranslation();
  return (
    <div
      className="mt-2 rounded border border-amber-400 p-2 text-sm"
      role="dialog"
      aria-label={t(
        'support.mcpServer.confirmTitle',
        'Restart the MCP server?'
      )}
    >
      <p>
        {status.running
          ? t(
              'support.mcpServer.confirmStop',
              'This stops the MCP server on port {{port}} (pid {{pid}}) and starts a new one.',
              { port: status.port, pid: status.pid }
            )
          : t(
              'support.mcpServer.confirmStart',
              'This starts a new MCP server on port {{port}}.',
              {
                port: status.port,
              }
            )}{' '}
        {t(
          'support.mcpServer.confirmBackground',
          'The new server runs in the background, logging to {{log}}. If the current one was started with run-mcp-server in a terminal, stopping it ends that terminal’s server; the new one does not run there.',
          { log: status.log_path ?? 'logs/mcp-server.log' }
        )}
      </p>
      <div className="mt-2 flex gap-2">
        <button
          type="button"
          onClick={onConfirm}
          className="rounded bg-amber-600 px-3 py-1 text-white"
        >
          {t('support.mcpServer.confirm', 'Confirm restart')}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="rounded bg-gray-200 px-3 py-1"
        >
          {t('common.cancel', 'Cancel')}
        </button>
      </div>
    </div>
  );
}

function RestartOutcome({ result }: { result: McpServerRestartResult }) {
  const { t } = useTranslation();
  if (result.restarted) {
    return (
      <p className="mt-2 text-sm text-green-600" role="status">
        {t(
          'support.mcpServer.restarted',
          'Restarted: pid {{pid}}, {{count}} tool(s).',
          {
            pid: result.pid ?? '?',
            count: result.tool_count ?? 0,
          }
        )}
      </p>
    );
  }
  return (
    <div className="mt-2 text-sm">
      <p className="text-red-600" role="alert">
        {result.reason ?? t('support.mcpServer.failed', 'Restart failed.')}
      </p>
      {result.log_lines.length > 0 && (
        <pre
          aria-label={t('support.mcpServer.logLines', 'MCP server log')}
          className="mt-1 max-h-60 overflow-auto whitespace-pre-wrap rounded bg-black/5 p-2 text-xs"
        >
          {result.log_lines.join('\n')}
        </pre>
      )}
    </div>
  );
}

/**
 * Status and restart of the local allotmint-pro MCP server (#9654).
 *
 * Renders nothing when the backend does not expose the route, which is the
 * case for every non-local deployment: on AWS the MCP server is a Lambda.
 * `onRestarted` lets the page reload its MCP tool list after a restart.
 */
export default function McpServerSection({
  onRestarted,
}: {
  onRestarted?: () => void;
}) {
  const { t } = useTranslation();
  const [supported, setSupported] = useState<boolean | null>(null);
  const [status, setStatus] = useState<McpServerStatus | null>(null);
  const [busy, setBusy] = useState<'checking' | 'restarting' | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<McpServerRestartResult | null>(null);

  const loadStatus = useCallback(async () => {
    setError(null);
    try {
      setStatus(await getMcpServerStatus());
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
    void loadStatus();
  }, [loadStatus]);

  async function handleRefresh() {
    setBusy('checking');
    await loadStatus();
    setBusy(null);
  }

  async function handleRestart() {
    setConfirming(false);
    setBusy('restarting');
    setError(null);
    setResult(null);
    try {
      const outcome = await restartMcpServer();
      setResult(outcome);
      if (outcome.restarted) onRestarted?.();
      await loadStatus();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  if (!supported) return null;

  return (
    <div className="mt-3 rounded border border-black/10 p-3">
      <h4 className="mb-1 font-semibold">
        {t('support.mcpServer.title', 'MCP server')}
      </h4>
      {status && <StatusSummary status={status} />}
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={handleRefresh}
          disabled={busy !== null}
          className="rounded bg-blue-600 px-3 py-1 text-sm text-white disabled:opacity-50"
        >
          {busy === 'checking'
            ? t('support.mcpServer.checking', 'Checking...')
            : t('support.mcpServer.refresh', 'Refresh status')}
        </button>
        <button
          type="button"
          onClick={() => setConfirming(true)}
          disabled={busy !== null || confirming || !status?.can_restart}
          className="rounded bg-amber-600 px-3 py-1 text-sm text-white disabled:opacity-50"
        >
          {busy === 'restarting'
            ? t('support.mcpServer.restarting', 'Restarting...')
            : t('support.mcpServer.restart', 'Restart MCP server')}
        </button>
      </div>
      {confirming && status && (
        <RestartConfirmation
          status={status}
          onConfirm={() => void handleRestart()}
          onCancel={() => setConfirming(false)}
        />
      )}
      {error && (
        <p className="mt-2 text-sm text-red-600" role="alert">
          {error}
        </p>
      )}
      {result && <RestartOutcome result={result} />}
    </div>
  );
}
