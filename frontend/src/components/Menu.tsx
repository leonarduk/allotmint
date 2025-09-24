// src/components/Menu.tsx
import { useEffect, useRef, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useConfig } from '../ConfigContext';
import type { TabPluginId } from '../tabPlugins';
import { orderedTabPlugins, SUPPORT_TABS } from '../tabPlugins';
import PomodoroTimer from './PomodoroTimer';
import { useFocusMode } from '../FocusModeContext';

const SUPPORT_ONLY_TABS: TabPluginId[] = [];

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

  const { focusMode, setFocusMode } = useFocusMode();

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

  let mode: TabPluginId;
  switch (path[0]) {
    case 'portfolio':
      mode = 'owner';
      break;
    case 'instrument':
      mode = 'instrument';
      break;
    case 'transactions':
      mode = 'transactions';
      break;
    case 'trading':
      mode = 'trading';
      break;
    case 'performance':
      mode = 'performance';
      break;
    case 'screener':
      mode = 'screener';
      break;
    case 'timeseries':
      mode = 'timeseries';
      break;
    case 'watchlist':
      mode = 'watchlist';
      break;
    case 'allocation':
      mode = 'allocation';
      break;
    case 'market':
      mode = 'market';
      break;
    case 'movers':
      mode = 'movers';
      break;
    case 'instrumentadmin':
      mode = 'instrumentadmin';
      break;
    case 'dataadmin':
      mode = 'dataadmin';
      break;
    case 'virtual':
      mode = 'virtual';
      break;
    case 'reports':
      mode = 'reports';
      break;
    case 'alert-settings':
      mode = 'alertsettings';
      break;
    case 'pension':
      mode = 'pension';
      break;
    case 'tax-tools':
      mode = 'taxtools';
      break;
    case 'support':
      mode = 'support';
      break;
    case 'settings':
      mode = 'settings';
      break;
    case 'scenario':
      mode = 'scenario';
      break;
    default:
      mode = path.length === 0 ? 'group' : 'movers';
  }

  const isSupportMode = (SUPPORT_TABS as readonly string[]).includes(mode as string);
  const inSupport = mode === 'support';
  const supportEnabled = tabs.support !== false && !disabledTabs?.includes('support');

  function pathFor(m: any) {
    switch (m) {
      case 'group':
        return selectedGroup ? `/?group=${selectedGroup}` : '/';
      case 'instrument':
        return selectedGroup ? `/instrument/${selectedGroup}` : '/instrument';
      case 'owner':
        return selectedOwner ? `/portfolio/${selectedOwner}` : '/portfolio';
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
      case 'alertsettings':
        return '/alert-settings';
      case 'settings':
        return '/settings';
      case 'allocation':
        return '/allocation';
      case 'rebalance':
        return '/rebalance';
      case 'instrumentadmin':
        return '/instrumentadmin';
      case 'pension':
        return '/pension/forecast';
      case 'taxtools':
        return '/tax-tools';
      default:
        return `/${m}`;
    }
  }

  return (
    <nav className="mb-4" ref={containerRef}>
      <button
        aria-expanded={open}
        aria-label={t('app.menu')}
        className="mb-2 p-2 border rounded"
        onClick={() => setOpen((o) => !o)}
      >
        ☰
      </button>
      {focusMode ? (
        <div className="flex flex-col" style={style}>
          <PomodoroTimer />
          <button
            type="button"
            onClick={() => setFocusMode(false)}
            className="mt-2 mr-4 bg-transparent border-0 p-0 cursor-pointer self-start"
          >
            {t('app.exitFocusMode')}
          </button>
        </div>
      ) : (
        <div
          hidden={!open}
          aria-hidden={!open}
          className={`${open ? 'flex md:flex' : 'hidden'} flex-col gap-2 md:flex-row md:flex-wrap`}
          style={style}
        >
          {orderedTabPlugins
            .filter((p) => p.section === (isSupportMode ? 'support' : 'user'))
            .slice()
            .sort((a, b) => a.priority - b.priority)
            .filter((p) => {
              if (p.id === 'support') return false;
              if (!inSupport && SUPPORT_ONLY_TABS.includes(p.id)) return false;
              const enabled = (tabs as Record<string, boolean | undefined>)[p.id] === true;
              return enabled && !disabledTabs?.includes(p.id);
            })
            .map((p) => (
              <Link
                key={p.id}
                to={pathFor(p.id as string)}
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
          <button
            type="button"
            onClick={() => setFocusMode(true)}
            className="mr-4 bg-transparent border-0 p-0 cursor-pointer"
          >
            {t('app.focusMode')}
          </button>
        </div>
      )}
    </nav>
  );
}
