import { useTranslation } from 'react-i18next';

/**
 * Shown on the admin pages while the backend's startup warm-up is still
 * running and the list on screen is partial (#10754). The page re-polls on
 * its own (see `useAdminScan`), so this only explains why rows are missing.
 */
export default function AdminWarmingNotice({ count }: { count: number }) {
  const { t } = useTranslation();
  return (
    <p
      role="status"
      data-testid="admin-warming-notice"
      className="admin-warming-notice mb-2 text-sm"
    >
      {t('admin.cacheWarming', {
        count,
        defaultValue:
          'Still loading after a server restart: showing the {{count}} found so far. This list fills in automatically.',
      })}
    </p>
  );
}
