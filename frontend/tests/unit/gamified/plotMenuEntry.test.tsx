import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import i18n from '@/i18n';
import Menu from '@/components/Menu';
import { configContext, type ConfigContextValue } from '@/ConfigContext';
import {
  buildPathForMode,
  deriveModeFromPathname,
  getMenuEntries,
  pageManifestByMode,
  standaloneRouteNeedsChrome,
} from '@/pageManifest';

const config: ConfigContextValue = {
  configLoaded: true,
  relativeViewEnabled: false,
  familyMvpEnabled: false,
  disabledTabs: [],
  tabs: { group: true, plot: true } as ConfigContextValue['tabs'],
  theme: 'dark',
  baseCurrency: 'GBP',
  refreshConfig: async () => {},
  setRelativeViewEnabled: () => {},
  setBaseCurrency: () => {},
};

describe('Plot mode route registration', () => {
  it('routes /plot and its nested screens to the plot mode', () => {
    expect(deriveModeFromPathname('/plot')).toBe('plot');
    expect(deriveModeFromPathname('/plot/crops')).toBe('plot');
    expect(deriveModeFromPathname('/plot/crops/VUSA.L')).toBe('plot');
    expect(buildPathForMode('plot')).toBe('/plot');
  });

  it('mounts as a wildcard standalone route with its own chrome', () => {
    const entry = pageManifestByMode.plot;
    // The wildcard keeps PlotApp's nested <Routes> resolving, and opting out
    // of AppHeader is what lets the skin render full-bleed.
    expect(entry.routePath).toBe('/plot/*');
    expect(entry.lazyComponent).toBeTruthy();
    expect(standaloneRouteNeedsChrome('/plot/*')).toBe(false);
  });

  it('appears in the dashboard menu category', () => {
    const dashboard = getMenuEntries('user').filter(
      (entry) => entry.menuCategory === 'dashboard'
    );
    expect(dashboard.some((entry) => entry.mode === 'plot')).toBe(true);
  });

  it('renders a nav link into the classic menu', () => {
    render(
      <configContext.Provider value={config}>
        <MemoryRouter>
          <Menu />
        </MemoryRouter>
      </configContext.Provider>
    );

    fireEvent.click(
      screen.getByRole('button', {
        name: i18n.t('app.menuCategories.dashboard'),
      })
    );
    const link = screen.getByRole('menuitem', {
      name: i18n.t('app.modes.plot'),
    });
    expect(link).toHaveAttribute('href', '/plot');
  });

  it('is hidden when the plot tab is switched off in config', () => {
    render(
      <configContext.Provider
        value={{
          ...config,
          tabs: { group: true, plot: false } as ConfigContextValue['tabs'],
        }}
      >
        <MemoryRouter>
          <Menu />
        </MemoryRouter>
      </configContext.Provider>
    );

    fireEvent.click(
      screen.getByRole('button', {
        name: i18n.t('app.menuCategories.dashboard'),
      })
    );
    expect(
      screen.queryByRole('menuitem', { name: i18n.t('app.modes.plot') })
    ).toBeNull();
  });
});
