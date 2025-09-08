// src/components/Menu.tsx
import { useEffect, useRef, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useConfig } from '../ConfigContext';
import type { TabPluginId } from '../tabPlugins';
import { orderedTabPlugins, SUPPORT_TABS } from '../tabPlugins';

const SUPPORT_ONLY_TABS: TabPluginId[] = ['logs'];

interface MenuProps {
  selectedOwner?: string;
  selectedGroup?: string;
  onLogout?: () => void;
  style?: React.CSSProperties;
}

export default function Menu({
  selectedOwner = '',
  selectedGroup = '',
  onLogout,
  style,
}: MenuProps) {
  const location = useLocation();
  const { t } = useTranslation();
  const { tabs, disabledTabs } = useConfig();
  const path = location.pathname.split('/').filter(Boolean);

  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleFocus(e: FocusEvent) {
      if (open && containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener('focusin', handleFocus);
    return () => {
      document.removeEventListener('focusin', handleFocus);
    };
  }, [open]);

  const mode: TabPluginId =
    path[0] === 'member'
      ? 'owner'
      : path[0] === 'instrument'
        ? 'instrument'
        : path[0] === 'transactions'
          ? 'transactions'
          : path[0] === 'trading'
            ? 'trading'
            : path[0] === 'performance'
              ? 'performance'
              : path[0] === 'screener'
                ? 'screener'
                : path[0] === 'timeseries'
                  ? 'timeseries'
                  : path[0] === 'watchlist'
                    ? 'watchlist'
                    : path[0] === 'allocation'
                      ? 'allocation'
                      : path[0] === 'market'
                        ? 'market'
                        : path[0] === 'movers'
                          ? 'movers'
                        : path[0] === 'instrumentadmin'
                          ? 'instrumentadmin'
                          : path[0] === 'dataadmin'
                            ? 'dataadmin'
                            : path[0] === 'profile'
                              ? 'profile'
                              : path[0] === 'virtual'
                                ? 'virtual'
                                : path[0] === 'reports'
                                  ? 'reports'
                                  : path[0] === 'support'
                                    ? 'support'
                                    : path[0] === 'settings'
                                      ? 'settings'
                                      : path[0] === 'scenario'
                                        ? 'scenario'
                                        : path[0] === 'logs'
                                          ? 'logs'
                                          : path.length === 0
                                            ? 'group'
                                            : 'movers';

  const isSupportMode = SUPPORT_TABS.includes(mode);
  const inSupport = mode === 'support';
  const supportEnabled = tabs.support !== false && !disabledTabs?.includes('support');

  function pathFor(m: TabPluginId) {
    switch (m) {
      case 'group':
        return selectedGroup ? `/?group=${selectedGroup}` : '/';
      case 'instrument':
        return selectedGroup ? `/instrument/${selectedGroup}` : '/instrument';
      case 'owner':
        return selectedOwner ? `/member/${selectedOwner}` : '/member';
      case 'performance':
        return selectedOwner ? `/performance/${selectedOwner}` : '/performance';
      case 'movers':
        return '/movers';
      case 'trading':
        return '/trading';
      case 'scenario':
        return '/scenario';
      case 'reports':
        return '/reports';
      case 'settings':
        return '/settings';
      case 'logs':
        return '/logs';
      case 'allocation':
        return '/allocation';
      case 'rebalance':
        return '/rebalance';
      case 'instrumentadmin':
        return '/instrumentadmin';
      case 'profile':
        return '/profile';
      default:
        return `/${m}`;
    }
  }

  return (
    <nav className="mb-4" ref={containerRef}>
      <button
        aria-label="menu"
        className="md:hidden mb-2 p-2 border rounded"
        onClick={() => setOpen((o) => !o)}
      >
        ☰
      </button>
      <div
        className={`${open ? 'flex' : 'hidden'} flex-col gap-2 md:flex md:flex-row md:flex-wrap`}
        style={style}
      >
        {orderedTabPlugins
          .filter((p) => p.section === (isSupportMode ? 'support' : 'user'))
          .slice()
          .sort((a, b) => a.priority - b.priority)
          .filter((p) => {
            if (p.id === 'support') return false;
            if (!inSupport && SUPPORT_ONLY_TABS.includes(p.id)) return false;
            return tabs[p.id] !== false && !disabledTabs?.includes(p.id);
          })
          .map((p) => (
            <Link
              key={p.id}
              to={pathFor(p.id)}
              className={`mr-4 ${mode === p.id ? 'font-bold' : ''} break-words`}
              style={{ fontWeight: mode === p.id ? 'bold' as const : undefined }}
              onClick={() => setOpen(false)}
            >
              {t(`app.modes.${p.id}`)}
            </Link>
          ))}
        {supportEnabled && (
          <Link
            to={inSupport ? '/' : '/support'}
            className={`mr-4 ${inSupport ? 'font-bold' : ''} break-words`}
            onClick={() => setOpen(false)}
          >
            {t('app.supportLink')}
          </Link>
        )}
        {onLogout && (
          <button
            type="button"
            onClick={() => {
              onLogout();
              setOpen(false);
            }}
            className="mr-4 bg-transparent border-0 p-0 cursor-pointer"
          >
            {t('app.logout')}
          </button>
        )}
      </div>
    </nav>
  );
}
