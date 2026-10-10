import { useTranslation } from 'react-i18next';
import { useWorkspaceTabs } from '../contexts/workspaceTabs';

/** Settings switch for the optional in-app workspace tabs (#10576). */
export default function WorkspaceTabsToggle() {
  const { t } = useTranslation();
  const { enabled, setEnabled } = useWorkspaceTabs();
  return (
    <section className="space-y-1 rounded-lg border p-4">
      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={enabled}
          onChange={(e) => setEnabled(e.target.checked)}
          aria-describedby="workspaceTabs-help"
        />
        <span>{t('workspaceTabs.toggle')}</span>
      </label>
      <p
        id="workspaceTabs-help"
        className="text-xs text-gray-600 dark:text-gray-400"
      >
        {t('workspaceTabs.toggleHelp')}
      </p>
    </section>
  );
}
