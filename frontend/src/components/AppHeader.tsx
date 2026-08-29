import { useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { LanguageSwitcher } from './LanguageSwitcher';
import Menu from './Menu';
import { InstrumentSearchBarToggle } from './InstrumentSearchBar';
import { NotificationsDrawer } from './NotificationsDrawer';
import UserAvatar from './UserAvatar';

interface AppHeaderProps {
  selectedOwner?: string;
  selectedGroup?: string;
  onLogout?: () => void;
  lastRefresh?: string | null;
  /** Extra header content, e.g. an owner selector, rendered between the nav and the refresh badge. */
  children?: ReactNode;
  /**
   * #7205: the /research empty state renders its own InstrumentSearchBar
   * inline so "choose a ticker from search" is immediately actionable. If
   * the header's search toggle stayed available too, opening both would put
   * two "Search instruments" inputs (and two sets of sector/region filters)
   * on screen at once — the issue explicitly forbids that double-up. The
   * caller (App.tsx) sets this while mode is 'research' with no ticker.
   */
  hideSearchToggle?: boolean;
}

/**
 * Shared header row (language switcher, nav, notifications, search, avatar) used by
 * every top-level page so standalone routes match the layout rendered inside App.tsx (#5736).
 */
export default function AppHeader({
  selectedOwner,
  selectedGroup,
  onLogout,
  lastRefresh,
  children,
  hideSearchToggle = false,
}: AppHeaderProps) {
  const { t } = useTranslation();
  const [notificationsOpen, setNotificationsOpen] = useState(false);

  return (
    <>
      <div
        className="flex-wrap-row"
        style={{
          alignItems: 'center',
          gap: '0.5rem',
          margin: '1rem 0',
        }}
      >
        <LanguageSwitcher />
        <Menu
          selectedOwner={selectedOwner}
          selectedGroup={selectedGroup}
          onLogout={onLogout}
          style={{ margin: 0 }}
        />
        {children}
        {lastRefresh && (
          <span
            style={{
              background: '#eee',
              borderRadius: '1rem',
              padding: '0.25rem 0.5rem',
              fontSize: '0.75rem',
            }}
            title={t('app.last') ?? undefined}
          >
            {new Date(lastRefresh).toLocaleString()}
          </span>
        )}
        {!hideSearchToggle && <InstrumentSearchBarToggle />}
        <button
          aria-label="notifications"
          onClick={() => setNotificationsOpen(true)}
          style={{
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            fontSize: '1.5rem',
          }}
        >
          🔔
        </button>
        <UserAvatar />
      </div>
      <NotificationsDrawer
        open={notificationsOpen}
        onClose={() => setNotificationsOpen(false)}
      />
    </>
  );
}
