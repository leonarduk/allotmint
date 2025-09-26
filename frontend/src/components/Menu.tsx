// src/components/Menu.tsx
import { useMemo, useRef, useState } from 'react';
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
    { id: 'dashboard', titleKey: 'dashboard', tabIds: ['group', 'market', 'movers'] },
    {
      id: 'holdings',
      titleKey: 'holdings',
      tabIds: ['owner', 'performance', 'allocation', 'transactions', 'reports'],
    },
    {
      id: 'tradeTools',
      titleKey: 'tradeTools',
      tabIds: [
        'instrument',
        'screener',
        'watchlist',
        'scenario',
        'trading',
        'rebalance',
        'tradecompliance',
      ],
    },
    { id: 'goals', titleKey: 'goals', tabIds: ['pension', 'taxtools', 'trail'] },
    { id: 'preferences', titleKey: 'preferences', tabIds: ['alertsettings', 'settings'] },
  ];

  const SUPPORT_MENU_CATEGORIES: MenuCategory[] = [
    {
      id: 'operations',
      titleKey: 'operations',
      tabIds: ['instrumentadmin', 'dataadmin', 'timeseries', 'support'],
    },
  ];

  const availableTabs = useMemo(
    () =>
      orderedTabPlugins
        .filter((p) => p.section === (isSupportMode ? 'support' : 'user'))
        .slice()
        .sort((a, b) => a.priority - b.priority)
        .filter((p) => {
          if (p.id === 'support') return false;
          if (!inSupport && SUPPORT_ONLY_TABS.includes(p.id)) return false;
          const enabled = (tabs as Record<string, boolean | undefined>)[p.id] === true;
          return enabled && !disabledTabs?.includes(p.id);
        }),
    [disabledTabs, inSupport, isSupportMode, tabs],
  );

  const categoryDefinitions = isSupportMode ? SUPPORT_MENU_CATEGORIES : USER_MENU_CATEGORIES;
  const categorizedTabIds = useMemo(
    () => new Set(categoryDefinitions.flatMap((category) => category.tabIds)),
    [categoryDefinitions],
  );

  const categoriesToRender: CategorizedMenu[] = useMemo(() => {
    const categories = categoryDefinitions
      .map((category) => ({
        ...category,
        tabs: availableTabs.filter((tab) => category.tabIds.includes(tab.id)),
      }))
      .filter((category) => category.tabs.length > 0);

    const uncategorizedTabs = availableTabs.filter((tab) => !categorizedTabIds.has(tab.id));

    if (uncategorizedTabs.length > 0) {
      categories.push({
        id: 'other',
        titleKey: 'other',
        tabIds: uncategorizedTabs.map((tab) => tab.id),
        tabs: uncategorizedTabs,
      });
    }

    return categories;
  }, [availableTabs, categorizedTabIds, categoryDefinitions]);

  const [openCategory, setOpenCategory] = useState<string | null>(null);
  const firstLinkRefs = useRef<Record<string, HTMLAnchorElement | null>>({});

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
    <nav className="mb-4" style={style}>
      <ul className="flex flex-wrap items-center gap-4 border-b border-gray-200 pb-4">
        {categoriesToRender.map((category) => {
          const isOpen = category.id === openCategory;
          const containsActiveTab = category.tabs.some((tab) => tab.id === mode);
          const buttonId = `menu-trigger-${category.id}`;
          const panelId = `menu-panel-${category.id}`;

          return (
            <li key={category.id} className="relative">
              <button
                id={buttonId}
                type="button"
                aria-expanded={isOpen}
                aria-controls={panelId}
                className={`flex min-w-[8rem] items-center justify-between gap-2 rounded px-3 py-2 text-sm font-medium transition-colors duration-150 focus:outline-none focus-visible:ring ${
                  isOpen || containsActiveTab
                    ? 'bg-gray-100 text-gray-900'
                    : 'bg-transparent text-gray-600 hover:bg-gray-100 hover:text-gray-900'
                }`}
                onClick={() =>
                  setOpenCategory((current) => (current === category.id ? null : category.id))
                }
                onKeyDown={(event) => {
                  if (event.key === 'ArrowDown') {
                    event.preventDefault();
                    if (!isOpen) {
                      setOpenCategory(category.id);
                    }
                    setTimeout(() => {
                      firstLinkRefs.current[category.id]?.focus();
                    }, 0);
                  } else if (event.key === 'Escape' && isOpen) {
                    event.preventDefault();
                    setOpenCategory(null);
                  }
                }}
              >
                <span className="truncate">
                  {t(`app.menuCategories.${category.titleKey}`)}
                </span>
                <span aria-hidden="true" className="text-xs">
                  {isOpen ? '▴' : '▾'}
                </span>
              </button>

              <div
                id={panelId}
                role="menu"
                aria-labelledby={buttonId}
                aria-hidden={!isOpen}
                className={`absolute left-0 right-auto top-full z-20 mt-2 w-max min-w-[12rem] rounded-md border border-[var(--drawer-border-color)] bg-[var(--drawer-bg)] p-3 text-[var(--drawer-text-color)] shadow-lg transition-[opacity,transform] duration-150 opacity-100 ${
                  isOpen ? 'block' : 'hidden'
                }`}
                onKeyDown={(event) => {
                  if (event.key === 'Escape') {
                    event.preventDefault();
                    setOpenCategory(null);
                  }
                }}

              >
                <ul className="flex flex-col gap-1">
                  {category.tabs.map((tab, index) => (
                    <li key={tab.id}>
                      <Link
                        ref={
                          index === 0
                            ? (element) => {
                                firstLinkRefs.current[category.id] = element;
                              }
                            : undefined
                        }
                        role="menuitem"
                        to={pathFor(tab.id as string)}
                        className={`block rounded px-2 py-1 text-sm transition-colors duration-150 focus:outline-none focus-visible:ring ${
                          mode === tab.id
                            ? 'font-semibold text-gray-900'
                            : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
                        }`}
                      >
                        {t(`app.modes.${tab.id}`)}
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            </li>
          );
        })}
      </ul>

      <div className="mt-6 flex flex-col gap-2 border-t border-gray-200 pt-4">
        {supportEnabled && (
          <Link
            to={inSupport ? '/' : '/support'}
            className={`${inSupport ? 'font-bold' : ''} break-words text-sm text-gray-600 hover:text-gray-900`}
          >
            {t('app.supportLink')}
          </Link>
        )}
        {onLogout && (
          <button
            type="button"
            onClick={() => {
              onLogout();
            }}
            className="bg-transparent border-0 p-0 text-left text-sm text-gray-600 hover:text-gray-900 cursor-pointer"
          >
            {t('app.logout')}
          </button>
        )}
      </div>
    </nav>
  );
}
