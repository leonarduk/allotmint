import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
} from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useConfig } from '../ConfigContext';
import { useAuth } from '../AuthContext';
import type { TabPluginId } from '../tabPlugins';
import { SUPPORT_TABS } from '../tabPlugins';
import {
  buildPathForMode,
  deriveModeFromLocation,
  getMenuEntries,
  MENU_CATEGORY_ORDER,
} from '../pageManifest';

interface MenuProps {
  selectedOwner?: string;
  selectedGroup?: string;
  onLogout?: () => void;
  style?: CSSProperties;
}

type MenuCategoryDefinition = {
  id: string;
  titleKey: string;
};

type MenuEntry = ReturnType<typeof getMenuEntries>[number];
type CategorizedMenu = MenuCategoryDefinition & { tabs: MenuEntry[] };

export default function Menu({
  selectedOwner = '',
  selectedGroup = '',
  onLogout,
  style,
}: MenuProps) {
  const location = useLocation();
  const { t } = useTranslation();
  const { tabs, disabledTabs } = useConfig();
  const { logout: contextLogout } = useAuth();
  // Fall back to the app-wide logout registered in AuthContext when the
  // caller doesn't thread one through explicitly, so the control stays
  // reachable regardless of where Menu is mounted (#4751).
  const effectiveLogout = onLogout ?? contextLogout ?? undefined;
  const mode = deriveModeFromLocation(location.pathname, location.search) as TabPluginId;
  const isSupportMode = (SUPPORT_TABS as readonly string[]).includes(mode);

  const categoryDefinitions = useMemo<MenuCategoryDefinition[]>(() => {
    const section = isSupportMode ? 'support' : 'user';
    return MENU_CATEGORY_ORDER[section].map((category) => ({
      id: category,
      titleKey: category,
    }));
  }, [isSupportMode]);

  const availableTabs = useMemo(
    () =>
      getMenuEntries(isSupportMode ? 'support' : 'user').filter(
        (entry) =>
          // Family MVP no longer restricts which tabs appear (#4641): every
          // tab enabled in config is navigable from the menu. Visibility is
          // driven purely by the config tab gating below.
          tabs[entry.mode] === true && !disabledTabs?.includes(entry.mode)
      ),
    [disabledTabs, isSupportMode, tabs]
  );

  // Whether the operations menu (Data Admin/Data Quality/Timeseries/Support/
  // ...) has anything to show at all -- i.e. whether the gateway link into it
  // (below) would land on an empty category. Computed independently of
  // `availableTabs`/`isSupportMode` because the gateway itself is only ever
  // rendered from the *user*-section menu (#7226).
  const operationsAvailable = useMemo(
    () =>
      getMenuEntries('support').some(
        (entry) =>
          entry.menuCategory === 'operations' &&
          tabs[entry.mode] === true &&
          !disabledTabs?.includes(entry.mode)
      ),
    [disabledTabs, tabs]
  );

  const categoriesToRender = useMemo<CategorizedMenu[]>(
    () =>
      categoryDefinitions
        .map((category) => ({
          ...category,
          tabs: availableTabs.filter((tab) => tab.menuCategory === category.id),
        }))
        .filter((category) => {
          if (category.tabs.length > 0) return true;
          // The Glossary link (below) always renders in 'preferences', so
          // that category is never actually empty — but keep the explicit
          // check so this stays readable if the Glossary link ever becomes
          // conditional again.
          return category.id === 'preferences';
        }),
    [availableTabs, categoryDefinitions]
  );

  const [openCategory, setOpenCategory] = useState<string | null>(null);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const firstLinkRefs = useRef<Record<string, HTMLElement | null>>({});
  const mobileMenuRef = useRef<HTMLElement | null>(null);

  // Close mobile menu and open category on route change
  useEffect(() => {
    setMobileMenuOpen(false);
    setOpenCategory(null);
  }, [location.pathname]);

  // Close mobile menu when clicking outside or pressing Escape
  useEffect(() => {
    if (!mobileMenuOpen) return;

    const handleClickOutside = (event: MouseEvent) => {
      if (
        mobileMenuRef.current &&
        !mobileMenuRef.current.contains(event.target as Node)
      ) {
        setMobileMenuOpen(false);
      }
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setMobileMenuOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [mobileMenuOpen]);

  const registerFirstFocusable =
    (categoryId: string) => (element: HTMLElement | null) => {
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
    <nav
      className="mb-4"
      style={style}
      ref={mobileMenuRef as React.Ref<HTMLElement>}
    >
      <button
        type="button"
        aria-expanded={mobileMenuOpen}
        aria-controls="app-main-menu"
        className="mb-3 inline-flex min-h-11 min-w-11 items-center justify-center rounded border border-gray-300 px-4 text-sm font-medium text-gray-700 sm:hidden"
        onClick={() => setMobileMenuOpen((current) => !current)}
      >
        {mobileMenuOpen ? t('app.close') : t('app.menu')}
      </button>
      <ul
        id="app-main-menu"
        className={`${mobileMenuOpen ? 'flex' : 'hidden'} list-none flex-col gap-3 border-b border-gray-200 pb-4 sm:flex sm:flex-row sm:flex-wrap sm:items-center sm:gap-4`}
      >
        {categoriesToRender.map((category) => {
          const isOpen = category.id === openCategory;
          const containsActiveTab = category.tabs.some(
            (tab) => tab.mode === mode
          );
          const buttonId = `menu-trigger-${category.id}`;
          const panelId = `menu-panel-${category.id}`;
          const assignFirstFocusable = registerFirstFocusable(category.id);

          return (
            <li key={category.id} className="relative w-full sm:w-auto">
              <button
                id={buttonId}
                type="button"
                aria-expanded={isOpen}
                aria-controls={panelId}
                className={`flex min-h-11 w-full items-center justify-between gap-2 rounded border-b-2 px-3 py-2 text-sm font-medium transition-colors duration-150 focus:outline-none focus-visible:ring sm:min-w-[8rem] sm:w-auto ${
                  isOpen || containsActiveTab
                    ? 'border-blue-600 bg-gray-100 text-gray-900'
                    : 'border-transparent bg-transparent text-gray-600 hover:bg-gray-100 hover:text-gray-900'
                }`}
                onClick={() =>
                  setOpenCategory((current) =>
                    current === category.id ? null : category.id
                  )
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
                className={`z-20 mt-2 min-w-[12rem] rounded-md border border-[var(--drawer-border-color)] bg-[var(--drawer-bg)] p-3 text-[var(--drawer-text-color)] shadow-lg transition-[opacity,transform] duration-150 opacity-100 sm:absolute sm:left-0 sm:right-auto sm:top-full sm:w-max ${
                  isOpen ? 'block' : 'hidden'
                }`}
                onKeyDown={(event) => {
                  if (event.key === 'Escape') {
                    event.preventDefault();
                    setOpenCategory(null);
                  }
                }}
              >
                <ul className="flex list-none flex-col gap-2">
                  {category.tabs.map((tab) => (
                    <li key={tab.mode}>
                      <Link
                        ref={assignFirstFocusable}
                        role="menuitem"
                        to={buildPathForMode(tab.mode, {
                          owner: selectedOwner,
                          group: selectedGroup,
                        })}
                        className={`block min-h-11 w-full rounded px-3 py-2 text-sm transition-colors duration-150 focus:outline-none focus-visible:ring ${
                          mode === tab.mode
                            ? 'font-semibold text-gray-900'
                            : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
                        }`}
                      >
                        {t(`app.modes.${tab.mode}`)}
                      </Link>
                    </li>
                  ))}
                  {category.id === 'preferences' && (
                    <li key="glossary">
                      <Link
                        ref={assignFirstFocusable}
                        role="menuitem"
                        to="/metrics-explained"
                        className={`block min-h-11 w-full rounded px-3 py-2 text-sm transition-colors duration-150 focus:outline-none focus-visible:ring ${
                          location.pathname === '/metrics-explained'
                            ? 'font-semibold text-gray-900'
                            : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
                        }`}
                      >
                        {t('app.glossaryLink', 'Glossary')}
                      </Link>
                    </li>
                  )}
                  {category.id === 'preferences' &&
                    !isSupportMode &&
                    operationsAvailable && (
                      // The only way into the operations menu (Data Admin,
                      // Data Quality, Timeseries, the Support console, ...)
                      // from the end-user menu. Deliberately generic --
                      // unlike the old "Support" link this replaces, it
                      // doesn't claim to be end-user help (#7226).
                      <li key="operations-gateway">
                        <Link
                          ref={assignFirstFocusable}
                          role="menuitem"
                          to={buildPathForMode('support')}
                          className="block min-h-11 w-full rounded px-3 py-2 text-sm text-gray-600 transition-colors duration-150 hover:bg-gray-100 hover:text-gray-900 focus:outline-none focus-visible:ring"
                        >
                          {t('app.operationsLink', 'Operations')}
                        </Link>
                      </li>
                    )}
                  {category.id === 'preferences' && isSupportMode && (
                    // The way back to the main app from any operations page
                    // -- without it, the operations menu (which replaces the
                    // dashboard/insights/goals categories while here) would
                    // strand the user with no nav path home (#7226).
                    <li key="back-to-app">
                      <Link
                        ref={assignFirstFocusable}
                        role="menuitem"
                        to={buildPathForMode('group', { group: selectedGroup })}
                        className="block min-h-11 w-full rounded px-3 py-2 text-sm text-gray-600 transition-colors duration-150 hover:bg-gray-100 hover:text-gray-900 focus:outline-none focus-visible:ring"
                      >
                        {t('app.userLink')}
                      </Link>
                    </li>
                  )}
                  {category.id === 'preferences' && effectiveLogout && (
                    <li key="logout">
                      <button
                        ref={(element) => assignFirstFocusable(element)}
                        type="button"
                        role="menuitem"
                        onClick={effectiveLogout}
                        className={`block min-h-11 w-full rounded px-3 py-2 text-left text-sm text-white bg-red-500 transition-colors duration-150 hover:bg-red-600 focus:outline-none focus-visible:ring`}
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
