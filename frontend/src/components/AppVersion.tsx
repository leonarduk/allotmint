import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { getApiBase } from '../api';
import { UI_VERSION } from '../appVersion';

/**
 * Shows the frontend's build version and the backend's version from the
 * public GET /health. They deploy in separate stacks, so after a partial or
 * failed deploy they can differ.
 */
export default function AppVersion() {
  const { t } = useTranslation();
  const [apiVersion, setApiVersion] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetch(`${getApiBase()}/health`, { signal: controller.signal })
      .then((res) => (res.ok ? res.json() : null))
      .then((body: { version?: unknown } | null) => {
        setApiVersion(typeof body?.version === 'string' ? body.version : '?');
      })
      .catch((err: unknown) => {
        if (!controller.signal.aborted) {
          console.warn('Could not read the backend version from /health', err);
          setApiVersion('?');
        }
      });
    return () => controller.abort();
  }, []);

  return (
    <p
      className="mt-2 text-xs text-[var(--surface-muted-color)]"
      data-testid="app-version"
    >
      {t('app.versionUi', 'UI')} {UI_VERSION} · {t('app.versionApi', 'API')}{' '}
      {apiVersion ?? '…'}
    </p>
  );
}
