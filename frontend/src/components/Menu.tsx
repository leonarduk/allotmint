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
  getPageManifestEntry,
  MENU_CATEGORY_ORDER,
} from '../pageManifest';
import { APP_TAB_NAME, OPERATIONS_TAB_NAME } from '../tabNames';

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

// Shared box styling for the admin menu's top-level App/Logout items, sized
// to line up with the category dropdown triggers.
const TOP_LEVEL_ITEM_CLASS =
  'flex min-h-11 w-full items-center rounded border-b-2 px-3 py-2 text-sm font-medium transition-colors duration-150 focus:outline-none focus-visible:ring sm:w-auto';

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
  const { tabs, disabledTabs, familyMvpEnabled } = useConfig();
  const { logout: contextLogout } = useAuth();
  // Fall back to the app-wide logout registered in AuthContext when the
  // caller doesn't thread one through explicitly, so the control stays
  // reachable regardless of where Menu is mounted (#4751).
  const effectiveLogout = onLogout ?? contextLogout ?? undefined;
  const mode = deriveModeFromLocation(location.pathname, location.search) as TabPluginId;
  const isSupportMode = (SUPPORT_TABS as readonly string[]).includes(mode);
  // A page folded into another menu item (e.g. /screener under Ideas) lights
  // up that item instead.
  const mergedIntoMode = getPageManifestEntry(mode)?.menuMergedInto;
  const isActiveTab = (tabMode: string) =>
    tabMode === mode || tabMode === mergedIntoMode;

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
          tabs[entry.mode] === true &&
          !disabledTabs?.includes(entry.mode) &&
          !(
            entry.menuMergedInto &&
            tabs[entry.menuMergedInto] === true &&
            !disabledTabs?.includes(entry.menuMergedInto)
          )
      ),
    [disabledTabs, isSupportMode, tabs]
  );

  // The first enabled operations entry (by priority, e.g. Timeseries before
  // Data Admin before ... before Support) -- i.e. what the gateway link
  // below actually targets. Computed independently of `availableTabs`/
  // `isSupportMode` because the gateway itself is only ever rendered from
  // the *user*-section menu (#7226). Targeting the first enabled entry
  // (rather than always /support) means the gateway still lands somewhere
  // real when Support specifically is disabled but e.g. Data Admin isn't.
  const firstOperationsEntry = useMemo(
    () =>
      getMenuEntries('support').find(
        (entry) =>
          entry.menuCategory === 'operations' &&
          tabs[entry.mode] === true &&
          !disabledTabs?.includes(entry.mode)
      ),
    [disabledTabs, tabs]
  );
  // Family MVP keeps the operations surface out of the simplified
  // experience -- the same gate the old bespoke "Support" link used to
  // apply (`!familyMvpEnabled`), preserved here for the gateway that
  // replaces it (#7226).
  const operationsGatewayVisible =
    !familyMvpEnabled && Boolean(firstOperationsEntry);

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

  // Close mobile menu and open category on route change. Skip the initial
  // mount: the effect would otherwise reset a category the user opened
  // between the first commit and the passive-effect flush (e.g. right after
  // a lazy route resolves), swallowing that first click.
  const lastPathnameRef = useRef(location.pathname);
  useEffect(() => {
    if (lastPathnameRef.current === location.pathname) return;
    lastPathnameRef.current = location.pathname;
    setMobileMenuOpen(false);
    setOpenCategory(null);
  }, [location.pathname]);

  // Name this tab after the surface it shows so the cross-links below can
  // target it (#9575).
  useEffect(() => {
    window.name = isSupportMode ? OPERATIONS_TAB_NAME : APP_TAB_NAME;
  }, [isSupportMode]);

  // The cross-links open in the other named tab, so this tab's route never
  // changes and the close-on-navigate effect above never fires.
  const closeMenus = () => {
    setOpenCategory(null);
    setMobileMenuOpen(false);
  };

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
        className="mb-3 inline-flex min-h-11 min-w-11 items-center justify-center rounded border border-[var(--menu-toggle-border)] px-4 text-sm font-medium text-[var(--menu-toggle-text)] sm:hidden"
        onClick={() => setMobileMenuOpen((current) => !current)}
      >
        {mobileMenuOpen ? t('app.close') : t('app.menu')}
      </button>
      <ul
        id="app-main-menu"
        className={`${mobileMenuOpen ? 'flex' : 'hidden'} list-none flex-col gap-3 border-b border-[var(--menu-border)] pb-4 sm:flex sm:flex-row sm:flex-wrap sm:items-center sm:gap-4`}
      >
        {categoriesToRender.map((category) => {
          const isOpen = category.id === openCategory;
          const containsActiveTab = category.tabs.some(
            (tab) => isActiveTab(tab.mode)
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
                    ? 'border-blue-600 bg-[var(--menu-active-bg)] text-[var(--menu-text-active)]'
                    : 'border-transparent bg-transparent text-[var(--menu-text)] hover:bg-[var(--menu-hover-bg)] hover:text-[var(--menu-text-active)]'
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
                {/* Item text colours use Tailwind's `!` (important) modifier so
                    they beat the unlayered global `a` / `a:hover` colours in
                    index.css, which otherwise outrank the utilities layer and
                    left items in the default link blue (#8609). */}
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
                          isActiveTab(tab.mode)
                            ? 'font-semibold text-[var(--menu-text-active)]!'
                            : 'text-[var(--menu-text)]! hover:bg-[var(--menu-hover-bg)] hover:text-[var(--menu-text-active)]!'
                        }`}
                      >
                        {t(`app.modes.${tab.menuLabelKey ?? tab.mode}`)}
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
                            ? 'font-semibold text-[var(--menu-text-active)]!'
                            : 'text-[var(--menu-text)]! hover:bg-[var(--menu-hover-bg)] hover:text-[var(--menu-text-active)]!'
                        }`}
                      >
                        {t('app.glossaryLink', 'Glossary')}
                      </Link>
                    </li>
                  )}
                  {category.id === 'preferences' &&
                    !isSupportMode &&
                    operationsGatewayVisible && (
                      // The only way into the operations menu (Data Admin,
                      // Data Quality, Timeseries, the Support console, ...)
                      // from the end-user menu. Deliberately generic --
                      // unlike the old "Support" link this replaces, it
                      // doesn't claim to be end-user help (#7226). Targets
                      // the first *enabled* operations entry rather than
                      // always /support, so it never lands on a disabled
                      // route (<DisabledFeature />) when Support itself is
                      // turned off but a sibling like Data Admin isn't.
                      // Opens in the named operations tab (reusing it if
                      // already open) so the console sits alongside the app
                      // instead of replacing it (#9575).
                      <li key="operations-gateway">
                        <Link
                          ref={assignFirstFocusable}
                          role="menuitem"
                          to={buildPathForMode(
                            firstOperationsEntry?.mode ?? 'support'
                          )}
                          target={OPERATIONS_TAB_NAME}
                          onClick={closeMenus}
                          className="block min-h-11 w-full rounded px-3 py-2 text-sm text-[var(--menu-text)]! transition-colors duration-150 hover:bg-[var(--menu-hover-bg)] hover:text-[var(--menu-text-active)]! focus:outline-none focus-visible:ring"
                        >
                          {t('app.operationsLink', 'Operations')}
                          <span aria-hidden="true"> ↗</span>{' '}
                          <span className="sr-only">
                            {t('app.opensInSeparateTab', '(opens in a separate tab)')}
                          </span>
                        </Link>
                      </li>
                    )}
                  {category.id === 'preferences' && effectiveLogout && (
                    // In the admin menu Logout is a top-level item instead.
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
        {isSupportMode && (
          // The admin menu has a single dropdown, so the way back to the
          // main app and Logout sit beside it as top-level items rather
          // than in a "Settings" dropdown of things that aren't settings.
          // Without the App link the admin menu would strand the user with
          // no nav path home (#7226). It targets the named app tab, so it
          // switches back to the app if it's open and opens it if not
          // (#9575).
          <li key="back-to-app" className="w-full sm:w-auto">
            <Link
              to={buildPathForMode('group', { group: selectedGroup })}
              target={APP_TAB_NAME}
              onClick={closeMenus}
              className={`${TOP_LEVEL_ITEM_CLASS} border-transparent text-[var(--menu-text)]! hover:bg-[var(--menu-hover-bg)] hover:text-[var(--menu-text-active)]!`}
            >
              {t('app.userLink')}
              <span aria-hidden="true"> ↗</span>{' '}
              <span className="sr-only">
                {t('app.opensInSeparateTab', '(opens in a separate tab)')}
              </span>
            </Link>
          </li>
        )}
        {isSupportMode && effectiveLogout && (
          <li key="logout" className="w-full sm:w-auto">
            <button
              type="button"
              onClick={effectiveLogout}
              className={`${TOP_LEVEL_ITEM_CLASS} border-transparent bg-red-500 text-white hover:bg-red-600`}
            >
              {t('app.logout')}
            </button>
          </li>
        )}
      </ul>
    </nav>
  );
}
