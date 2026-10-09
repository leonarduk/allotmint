import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  getBotsDigestHistory,
  getBotsDigestLatest,
  getBotsDigestPreview,
  type BotsDigest as Digest,
  type BotsDigestEntry,
} from '../api';

type Props = { owner: string };

type Load =
  | { kind: 'loading' }
  | { kind: 'empty' }
  | { kind: 'error' }
  | { kind: 'ready'; digest: Digest; preview: boolean };

const SEVERITY_COLOURS: Record<string, string> = {
  high: 'var(--color-danger, #b00020)',
  medium: 'var(--color-warning, #b26a00)',
  low: 'var(--color-muted, #666)',
  info: 'var(--color-muted, #666)',
};

function isNotFound(err: unknown): boolean {
  return (err as { status?: number })?.status === 404;
}

/** Safe href for an item link: app-relative or https only. */
function safeHref(link: string | null): string | undefined {
  if (!link) return undefined;
  if (link.startsWith('https://')) return link;
  if (link.startsWith('/') && !link.startsWith('//')) return link;
  return undefined;
}

function DigestItemRow({ item }: { item: BotsDigestEntry }) {
  const { t } = useTranslation();
  const href = safeHref(item.link);
  return (
    <li data-testid="bots-digest-item" style={{ marginBottom: '0.5rem' }}>
      <strong style={{ color: SEVERITY_COLOURS[item.severity] }}>
        {t(`botsDigest.severity.${item.severity}`)}
      </strong>{' '}
      {href ? <a href={href}>{item.title}</a> : item.title}{' '}
      <span className="muted">({t(`botsDigest.status.${item.status}`)})</span>
      {item.action_required && (
        <em style={{ marginLeft: '0.5rem' }}>
          {t('botsDigest.actionRequired')}
        </em>
      )}
      {item.summary && <div>{item.summary}</div>}
    </li>
  );
}

function DigestBody({ digest, preview }: { digest: Digest; preview: boolean }) {
  const { t } = useTranslation();
  const notRun = digest.bots
    .filter((b) => b.state === 'not_run_yet')
    .map((b) => b.name);
  const truncated = Object.values(digest.truncated).reduce((a, b) => a + b, 0);
  return (
    <div>
      {preview && <p className="muted">{t('botsDigest.previewNote')}</p>}
      <p data-testid="bots-digest-opener">{digest.opener}</p>
      {digest.items.length > 0 && (
        <ul style={{ paddingLeft: '1.25rem' }}>
          {digest.items.map((item) => (
            <DigestItemRow key={item.dedupe_key} item={item} />
          ))}
        </ul>
      )}
      {truncated > 0 && (
        <p className="muted">
          {t('botsDigest.truncated', { count: truncated })}
        </p>
      )}
      {digest.resolved.length > 0 && (
        <>
          <h4>{t('botsDigest.resolvedTitle')}</h4>
          <ul
            style={{ paddingLeft: '1.25rem' }}
            data-testid="bots-digest-resolved"
          >
            {digest.resolved.map((item) => (
              <li key={item.dedupe_key}>{item.title}</li>
            ))}
          </ul>
        </>
      )}
      {notRun.length > 0 && (
        <p className="muted">
          {t('botsDigest.notRunYet', { bots: notRun.join(', ') })}
        </p>
      )}
    </div>
  );
}

/** Ranked digest of what the bots found that needs the owner (#10485). */
export function BotsDigest({ owner }: Props) {
  const { t } = useTranslation();
  const [load, setLoad] = useState<Load>({ kind: 'loading' });
  const [history, setHistory] = useState<Digest[]>([]);

  useEffect(() => {
    let cancelled = false;
    setLoad({ kind: 'loading' });
    getBotsDigestLatest(owner)
      .then(
        (digest) =>
          !cancelled && setLoad({ kind: 'ready', digest, preview: false })
      )
      .catch(
        (err: unknown) =>
          !cancelled && setLoad({ kind: isNotFound(err) ? 'empty' : 'error' })
      );
    getBotsDigestHistory(owner)
      .then((res) => !cancelled && setHistory(res.digests))
      .catch(() => !cancelled && setHistory([])); // history is optional; the main view reports errors
    return () => {
      cancelled = true;
    };
  }, [owner]);

  const preview = () => {
    setLoad({ kind: 'loading' });
    getBotsDigestPreview(owner)
      .then((digest) => setLoad({ kind: 'ready', digest, preview: true }))
      .catch(() => setLoad({ kind: 'error' }));
  };

  return (
    <section data-testid="bots-digest" aria-labelledby="bots-digest-title">
      <h3 id="bots-digest-title">{t('botsDigest.title')}</h3>
      {load.kind === 'loading' && <p>{t('botsDigest.loading')}</p>}
      {load.kind === 'error' && <p role="alert">{t('botsDigest.error')}</p>}
      {load.kind === 'empty' && <p>{t('botsDigest.empty')}</p>}
      {load.kind === 'ready' && (
        <DigestBody digest={load.digest} preview={load.preview} />
      )}
      {load.kind !== 'loading' && (
        <button type="button" onClick={preview}>
          {t('botsDigest.preview')}
        </button>
      )}
      {history.length > 0 && (
        <>
          <h4>{t('botsDigest.history')}</h4>
          <ul
            style={{ paddingLeft: '1.25rem' }}
            data-testid="bots-digest-history"
          >
            {history.map((digest) => (
              <li key={digest.generated_at}>
                <button
                  type="button"
                  className="link-button"
                  onClick={() =>
                    setLoad({ kind: 'ready', digest, preview: false })
                  }
                >
                  {t('botsDigest.historyEntry', {
                    date: digest.generated_at.slice(0, 10),
                    count: digest.items.length,
                  })}
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

export default BotsDigest;
