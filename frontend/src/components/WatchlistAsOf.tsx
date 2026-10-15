import { useTranslation } from 'react-i18next';
import { WATCHLIST_META, type WatchlistMeta } from '../data/watchlists';

/**
 * Shows when a built-in watchlist's constituents were last checked (#10912).
 * `name` is a plain string because callers may hold a name restored from
 * localStorage that no longer exists; unknown names render nothing.
 */
export function WatchlistAsOf({ name }: { name: string }) {
  const { t, i18n } = useTranslation();
  const meta: WatchlistMeta | undefined = Object.hasOwn(WATCHLIST_META, name)
    ? WATCHLIST_META[name as keyof typeof WATCHLIST_META]
    : undefined;
  if (!meta) return null;
  const { asOf, source } = meta;
  // asOf is a calendar date; format in UTC so it never shifts a day.
  const date = new Date(`${asOf}T00:00:00Z`).toLocaleDateString(i18n.language, {
    dateStyle: 'medium',
    timeZone: 'UTC',
  });
  return (
    <span
      data-testid="watchlist-as-of"
      style={{ color: '#64748b', fontSize: '0.75rem', marginRight: '0.5rem' }}
    >
      {t('watchlist.constituentsAsOf', { date, source })}
    </span>
  );
}
