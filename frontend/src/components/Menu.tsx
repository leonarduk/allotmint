// src/components/Menu.tsx
import { useMemo, useRef, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useConfig } from '../ConfigContext';
import type { TabPluginId } from '../tabPlugins';
import { SUPPORT_TABS } from '../tabPlugins';
import {
  buildPathForMode,
  deriveModeFromPathname,
  getMenuEntries,
  MENU_CATEGORY_ORDER,
} from '../pageManifest';

const SUPPORT_ONLY_TABS: TabPluginId[] = [];

interface MenuProps {
  selectedOwner?: string;
  selectedGroup?: string;
  onLogout?: () => void;
  style?: React.CSSProperties;
}

type MenuCategoryDefinition = {
  id: string;
  titleKey: string;
};

type CategorizedMenu = MenuCategoryDefinition & {
  tabs: ReturnType<typeof getMenuEntries>;
};

export default function Menu({
  selectedOwner = '',
  selectedGroup = '',
  onLogout,
  style,
}: MenuProps) {
  const location = useLocation();
  const { t } = useTranslation();
  const { tabs, disabledTabs } = useConfig();
  const mode = deriveModeFromPathname(location.pathname) as TabPluginId;

  const isSupportMode = (SUPPORT_TABS as readonly string[]).includes(mode as string);
  const inSupport = mode === 'support';
  const supportEnabled = tabs.support !== false && !disabledTabs?.includes('support');

  const categoryDefinitions = useMemo<MenuCategoryDefinition[]>(() => {
    const section = isSupportMode ? 'support' : 'user';
    return MENU_CATEGORY_ORDER[section].map((category) => ({
      id: category,
      titleKey: category,
    }));
  }, [isSupportMode]);

  const availableTabs = useMemo(
    () =>
      getMenuEntries(isSupportMode ? 'support' : 'user').filter((entry) => {
        if (entry.mode === 'support') return false;
        if (!inSupport && SUPPORT_ONLY_TABS.includes(entry.mode as TabPluginId)) {
          return false;
        }
        const enabled = tabs[entry.mode] === true;
        return enabled && !disabledTabs?.includes(entry.mode);
      }),
    [disabledTabs, inSupport, isSupportMode, tabs],
  );

  const categoriesToRender: CategorizedMenu[] = useMemo(() => {
    const categories = categoryDefinitions
      .map((category) => ({
        ...category,
        tabs: availableTabs.filter((tab) => tab.menu?.category === category.id),
      }))
      .filter((category) => {
        if (category.tabs.length > 0) return true;
        if (category.id === 'preferences') {
          return supportEnabled || Boolean(onLogout);
        }
        return false;
      });

    return categories;
  }, [availableTabs, categoryDefinitions, onLogout, supportEnabled]);

  const [openCategory, setOpenCategory] = useState<string | null>(null);
  const firstLinkRefs = useRef<Record<string, HTMLElement | null>>({});

  const registerFirstFocusable = (categoryId: string) => (element: HTMLElement | null) => {
    if (!element) {
      if (firstLinkRefs.current[categoryId]?.isConnected === false) {
        firstLinkRefs.current[categoryId] = null;
      }
      return;
    }

    const current = firstLinkRefs.current[categoryId];
    if (!current || current.isConnected === false) {
      firstLinkRefs.current[categoryId] = element;
    }
  };

  return (
    <nav className="mb-4" style={style}>
      <ul className="flex list-none flex-wrap items-center gap-4 border-b border-gray-200 pb-4">
        {categoriesToRender.map((category) => {
          const isOpen = category.id === openCategory;
          const containsActiveTab = category.tabs.some((tab) => tab.mode === mode);
          const buttonId = `menu-trigger-${category.id}`;
          const panelId = `menu-panel-${category.id}`;
          const assignFirstFocusable = registerFirstFocusable(category.id);

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
                <ul className="flex list-none flex-col gap-1">
                  {category.tabs.map((tab) => (
                    <li key={tab.mode}>
                      <Link
                        ref={assignFirstFocusable}
                        role="menuitem"
                        to={buildPathForMode(tab.mode, {
                          owner: selectedOwner,
                          group: selectedGroup,
                        })}
                        className={`block rounded px-2 py-1 text-sm transition-colors duration-150 focus:outline-none focus-visible:ring ${
                          mode === tab.mode
                            ? 'font-semibold text-gray-900'
                            : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
                        }`}
                      >
                        {t(`app.modes.${tab.mode}`)}
                      </Link>
                    </li>
                  ))}
                  {category.id === 'preferences' && supportEnabled && (
                    <li key="support">
                      <Link
                        ref={assignFirstFocusable}
                        role="menuitem"
                        to={inSupport ? buildPathForMode('group', { group: selectedGroup }) : buildPathForMode('support')}
                        className={`block rounded px-2 py-1 text-sm transition-colors duration-150 focus:outline-none focus-visible:ring ${
                          inSupport
                            ? 'font-semibold text-gray-900'
                            : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
                        }`}
                      >
                        {t('app.supportLink')}
                      </Link>
                    </li>
                  )}
                  {category.id === 'preferences' && onLogout && (
                    <li key="logout">
                      <button
                        ref={(element) => assignFirstFocusable(element)}
                        type="button"
                        role="menuitem"
                        onClick={() => {
                          onLogout();
                        }}
                        className="block w-full rounded px-2 py-1 text-left text-sm text-gray-600 transition-colors duration-150 hover:bg-gray-100 hover:text-gray-900 focus:outline-none focus-visible:ring"
                      >
                        {t('app.logout')}
                      </button>
                    </li>
                  )}
                </ul>
              </div>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
