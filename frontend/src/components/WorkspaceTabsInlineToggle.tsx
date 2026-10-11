import { useTranslation } from 'react-i18next';
import { useWorkspaceTabs } from '../contexts/workspaceTabs';

/**
 * Compact workspace-tabs switch shown next to "Relative view" on the pages
 * where tabs are most useful, so the feature isn't buried in Settings.
 */
export function WorkspaceTabsInlineToggle() {
  const { t } = useTranslation();
  const { enabled, setEnabled } = useWorkspaceTabs();

  return (
    <label
      title={t('workspaceTabs.toggleHelp')}
      style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem' }}
    >
      <input
        type="checkbox"
        checked={enabled}
        onChange={(e) => setEnabled(e.target.checked)}
      />
      {t('workspaceTabs.label')}
    </label>
  );
}
