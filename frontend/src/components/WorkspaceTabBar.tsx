import type { CSSProperties } from 'react';
import { useTranslation } from 'react-i18next';
import { useLocation } from 'react-router-dom';
import { useWorkspaceTabs } from '../contexts/workspaceTabs';
import {
  MAX_WORKSPACE_TABS,
  describeTabPath,
  type WorkspaceTab,
} from '../lib/workspaceTabs';
import { deriveModeFromPathname } from '../pageManifest';
import { CHAT_WINDOW_PATH } from '../utils/chatWindow';

// Same reasoning as AppHeader's ICON_BUTTON_PADDING: the global button
// padding would make each small control far wider than its glyph.
const iconButton: CSSProperties = {
  background: 'none',
  border: 'none',
  cursor: 'pointer',
  padding: '0 0.25rem',
  font: 'inherit',
  color: 'inherit',
};

function useTabLabel() {
  const { t } = useTranslation();
  return (tab: WorkspaceTab): string => {
    const label = describeTabPath(tab.path);
    if (label.kind === 'instrument') return label.ticker;
    if (label.kind === 'group') {
      const groupLabel = t('app.modes.group');
      return label.group ? `${groupLabel}: ${label.group}` : groupLabel;
    }
    const mode = deriveModeFromPathname(label.pathname);
    return t(`app.modes.${mode}`, { defaultValue: label.pathname });
  };
}

/**
 * Strip of in-app workspace tabs (#10576). Renders nothing unless the user
 * has switched tabs on in Settings.
 */
export default function WorkspaceTabBar() {
  const { t } = useTranslation();
  const { pathname } = useLocation();
  const {
    enabled,
    tabs,
    activeId,
    openCurrentInNewTab,
    selectTab,
    closeTab,
    refreshActive,
  } = useWorkspaceTabs();
  const labelFor = useTabLabel();

  // The detached chat window is a separate browser window, not a workspace.
  if (!enabled || pathname === CHAT_WINDOW_PATH) return null;

  return (
    <nav
      aria-label={t('workspaceTabs.label')}
      className="flex-wrap-row"
      style={{
        alignItems: 'center',
        gap: '0.25rem',
        borderBottom: '1px solid rgba(128, 128, 128, 0.4)',
        // Lines the first tab up with the header row below it.
        padding: '0.5rem 1rem 0',
      }}
    >
      {tabs.map((tab) => {
        const active = tab.id === activeId;
        const label = labelFor(tab);
        return (
          <div
            key={tab.id}
            style={{
              display: 'flex',
              alignItems: 'center',
              border: '1px solid rgba(128, 128, 128, 0.4)',
              borderBottom: active ? '2px solid currentColor' : undefined,
              borderRadius: '0.375rem 0.375rem 0 0',
              padding: '0.125rem 0.25rem',
              fontWeight: active ? 600 : 400,
            }}
          >
            <button
              type="button"
              aria-current={active ? 'page' : undefined}
              title={tab.path}
              onClick={() => selectTab(tab.id)}
              style={{
                ...iconButton,
                maxWidth: '14rem',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
            >
              {label}
            </button>
            {active && (
              <button
                type="button"
                aria-label={t('workspaceTabs.refresh', { label })}
                title={t('workspaceTabs.refresh', { label })}
                onClick={refreshActive}
                style={iconButton}
              >
                ↻
              </button>
            )}
            {tabs.length > 1 && (
              <button
                type="button"
                aria-label={t('workspaceTabs.close', { label })}
                title={t('workspaceTabs.close', { label })}
                onClick={() => closeTab(tab.id)}
                style={iconButton}
              >
                ×
              </button>
            )}
          </div>
        );
      })}
      <button
        type="button"
        aria-label={t('workspaceTabs.new')}
        title={t('workspaceTabs.new')}
        onClick={openCurrentInNewTab}
        disabled={tabs.length >= MAX_WORKSPACE_TABS}
        style={{ ...iconButton, fontSize: '1.25rem' }}
      >
        +
      </button>
    </nav>
  );
}
