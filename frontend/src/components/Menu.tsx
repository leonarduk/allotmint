// src/components/Menu.tsx
import { useEffect, useMemo, useState } from 'react';
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

  const [activeCategory, setActiveCategory] = useState<string | null>(null);

  useEffect(() => {
    const containingCategory = categoriesToRender.find((category) =>
      category.tabs.some((tab) => tab.id === mode),
    );
    if (containingCategory) {
      setActiveCategory((current) => current ?? containingCategory.id);
    } else if (!activeCategory && categoriesToRender.length > 0) {
      setActiveCategory(categoriesToRender[0].id);
    }
  }, [activeCategory, categoriesToRender, mode]);

  useEffect(() => {
    const containingCategory = categoriesToRender.find((category) =>
      category.tabs.some((tab) => tab.id === mode),
    );
    if (containingCategory && containingCategory.id !== activeCategory) {
      setActiveCategory(containingCategory.id);
    }
  }, [categoriesToRender, mode, activeCategory]);

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

  const activeCategoryDefinition = categoriesToRender.find(
    (category) => category.id === activeCategory,
  );

  return (
    <nav className="mb-4" style={style}>
      <div className="flex flex-wrap items-center gap-2 border-b border-gray-200 pb-2">
        {categoriesToRender.map((category) => {
          const isActive = category.id === activeCategory;
          return (
            <button
              key={category.id}
              type="button"
              className={`rounded-t px-3 py-2 text-sm font-medium transition-colors duration-150 focus:outline-none focus-visible:ring ${
                isActive
                  ? 'bg-gray-100 text-gray-900'
                  : 'bg-transparent text-gray-600 hover:bg-gray-100 hover:text-gray-900'
              }`}
              onClick={() => setActiveCategory(category.id)}
            >
              {t(`app.menuCategories.${category.titleKey}`)}
            </button>
          );
        })}
      </div>

      {activeCategoryDefinition && (
        <div className="mt-4 flex flex-col gap-6">
          <section className="flex flex-col gap-2">
            <h3 className="text-sm font-semibold uppercase tracking-wide text-gray-600">
              {t(`app.menuCategories.${activeCategoryDefinition.titleKey}`)}
            </h3>
            <ul className="flex flex-wrap gap-3">
              {activeCategoryDefinition.tabs.map((tab) => (
                <li key={tab.id}>
                  <Link
                    to={pathFor(tab.id as string)}
                    className={`text-sm transition-colors duration-150 ${
                      mode === tab.id ? 'font-bold text-gray-900' : 'text-gray-600 hover:text-gray-900'
                    }`}
                  >
                    {t(`app.modes.${tab.id}`)}
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        </div>
      )}

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
