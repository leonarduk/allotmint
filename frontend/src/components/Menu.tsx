// src/components/Menu.tsx
import { useEffect, useRef, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useConfig } from '../ConfigContext';
import type { TabPluginId } from '../tabPlugins';
import { orderedTabPlugins, SUPPORT_TABS } from '../tabPlugins';

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

  type TabDefinition = (typeof orderedTabPlugins)[number];

  type MenuCategory = {
    id: string;
    titleKey: string;
    tabIds: TabPluginId[];
  };

  type CategorizedMenu = MenuCategory & {
    tabs: TabDefinition[];
  };

  const USER_MENU_CATEGORIES: MenuCategory[] = [
    { id: 'overview', titleKey: 'overview', tabIds: ['group', 'market', 'movers'] },
    {
      id: 'portfolio',
      titleKey: 'portfolio',
      tabIds: ['owner', 'performance', 'transactions', 'trading', 'allocation', 'rebalance', 'trail'],
    },
    {
      id: 'research',
      titleKey: 'research',
      tabIds: ['instrument', 'screener', 'timeseries', 'watchlist', 'scenario'],
    },
    { id: 'reporting', titleKey: 'reporting', tabIds: ['reports', 'tradecompliance'] },
    { id: 'planning', titleKey: 'planning', tabIds: ['pension', 'taxtools'] },
    { id: 'settings', titleKey: 'settings', tabIds: ['settings'] },
  ];

  const SUPPORT_MENU_CATEGORIES: MenuCategory[] = [
    { id: 'supportTools', titleKey: 'supportTools', tabIds: ['instrumentadmin', 'dataadmin'] },
  ];

  const availableTabs = orderedTabPlugins
    .filter((p) => p.section === (isSupportMode ? 'support' : 'user'))
    .slice()
    .sort((a, b) => a.priority - b.priority)
    .filter((p) => {
      if (p.id === 'support') return false;
      if (!inSupport && SUPPORT_ONLY_TABS.includes(p.id)) return false;
      const enabled = (tabs as Record<string, boolean | undefined>)[p.id] === true;
      return enabled && !disabledTabs?.includes(p.id);
    });

  const categoryDefinitions = isSupportMode ? SUPPORT_MENU_CATEGORIES : USER_MENU_CATEGORIES;
  const categorizedTabIds = new Set(categoryDefinitions.flatMap((category) => category.tabIds));

  const categoriesToRender: CategorizedMenu[] = categoryDefinitions
    .map((category) => ({
      ...category,
      tabs: availableTabs.filter((tab) => category.tabIds.includes(tab.id)),
    }))
    .filter((category) => category.tabs.length > 0);

  const uncategorizedTabs = availableTabs.filter((tab) => !categorizedTabIds.has(tab.id));

  if (uncategorizedTabs.length > 0) {
    categoriesToRender.push({
      id: 'other',
      titleKey: 'other',
      tabIds: uncategorizedTabs.map((tab) => tab.id),
      tabs: uncategorizedTabs,
    });
  }

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
      <div
        hidden={!open}
        aria-hidden={!open}
        className={`${open ? 'flex' : 'hidden'} flex-col gap-6`}
        style={style}
      >
        {categoriesToRender.map((category) => (
          <section key={category.id} className="flex flex-col gap-2">
            <h3 className="text-sm font-semibold uppercase tracking-wide text-gray-600">
              {t(`app.menuCategories.${category.titleKey}`)}
            </h3>
            <ul className="flex flex-col gap-1">
              {category.tabs.map((tab) => (
                <li key={tab.id}>
                  <Link
                    to={pathFor(tab.id as string)}
                    className={`${mode === tab.id ? 'font-bold' : ''} break-words`}
                    style={{ fontWeight: mode === tab.id ? 'bold' as const : undefined }}
                    onClick={() => setOpen(false)}
                  >
                    {t(`app.modes.${tab.id}`)}
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        ))}
        <div className="flex flex-col gap-2 border-t border-gray-200 pt-4">
          {supportEnabled && (
            <Link
              to={inSupport ? '/' : '/support'}
              className={`${inSupport ? 'font-bold' : ''} break-words`}
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
              className="bg-transparent border-0 p-0 text-left cursor-pointer"
            >
              {t('app.logout')}
            </button>
          )}
        </div>
      </div>
    </nav>
  );
}
