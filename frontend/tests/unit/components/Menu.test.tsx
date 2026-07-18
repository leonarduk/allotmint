import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi } from 'vitest';
import i18n from '@/i18n';
import Menu from '@/components/Menu';
import { configContext, type ConfigContextValue } from '@/ConfigContext';
import { AuthContext } from '@/contexts/auth';

const configWithTransactions: ConfigContextValue = {
  relativeViewEnabled: false,
  disabledTabs: [],
  tabs: {
    group: true,
    market: true,
    owner: true,
    instrument: true,
    performance: true,
    transactions: true,
    screener: true,
    trading: true,
    timeseries: true,
    watchlist: true,
    allocation: true,
    rebalance: true,
    movers: true,
    instrumentadmin: true,
    dataadmin: true,
    virtual: true,
    support: true,
    settings: true,
    pension: true,
    reports: true,
    scenario: true,
  },
  theme: 'system',
  baseCurrency: 'GBP',
  refreshConfig: async () => {},
  setRelativeViewEnabled: () => {},
  setBaseCurrency: () => {},
};

/** Config that enables Family MVP mode — hides non-MVP categories like insights/goals. */
const familyMvpConfig: ConfigContextValue = {
  ...configWithTransactions,
  familyMvpEnabled: true,
};

describe('Menu', () => {
  it('hides links by default and shows them after toggle', async () => {
    render(
      <configContext.Provider value={configWithTransactions}>
        <MemoryRouter>
          <Menu />
        </MemoryRouter>
      </configContext.Provider>
    );
    const settingsToggle = screen.getByRole('button', {
      name: i18n.t('app.menuCategories.dashboard'),
    });
    expect(settingsToggle).toHaveAttribute('aria-expanded', 'false');
    expect(
      screen.queryByRole('menuitem', { name: 'Support' })
    ).not.toBeInTheDocument();
    fireEvent.click(settingsToggle);
    expect(settingsToggle).toHaveAttribute('aria-expanded', 'true');
    const inputLink = await screen.findByRole('menuitem', {
      name: i18n.t('app.modes.transactions'),
    });
    expect(inputLink).toBeVisible();
    expect(inputLink).toHaveAttribute('href', '/input');
    fireEvent.click(settingsToggle);
    expect(settingsToggle).toHaveAttribute('aria-expanded', 'false');
    await waitFor(() =>
      expect(
        screen.queryByRole('menuitem', {
          name: i18n.t('app.modes.transactions'),
        })
      ).not.toBeInTheDocument()
    );
  });

  it('updates aria-expanded attribute when toggled', () => {
    render(
      <MemoryRouter>
        <Menu />
      </MemoryRouter>
    );
    const settingsToggle = screen.getByRole('button', {
      name: i18n.t('app.menuCategories.dashboard'),
    });
    expect(settingsToggle).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(settingsToggle);
    expect(settingsToggle).toHaveAttribute('aria-expanded', 'true');
    fireEvent.click(settingsToggle);
    expect(settingsToggle).toHaveAttribute('aria-expanded', 'false');
  });

  it('keeps only Family MVP tabs on support route', async () => {
    render(
      <MemoryRouter initialEntries={['/support']}>
        <Menu />
      </MemoryRouter>
    );
    expect(
      screen.queryByRole('button', {
        name: i18n.t('app.menuCategories.dashboard'),
      })
    ).toBeNull();
    expect(
      screen.queryByRole('menuitem', { name: 'Support' })
    ).not.toBeInTheDocument();
  });

  it('hides the support link when the support tab is disabled', () => {
    // The preferences category still renders (settings, logout) — but the
    // Support link inside it must be absent when the support tab is disabled.
    const onLogout = vi.fn();
    const config: ConfigContextValue = {
      relativeViewEnabled: false,
      disabledTabs: ['support'],
      tabs: {
        group: true,
        market: true,
        owner: true,
        instrument: true,
        performance: true,
        transactions: true,
        screener: true,
        trading: true,
        timeseries: true,
        watchlist: true,
        allocation: true,
        rebalance: true,
        movers: true,
        instrumentadmin: true,
        dataadmin: true,
        virtual: true,
        support: false,
        settings: true,
        pension: true,
        reports: true,
        scenario: true,
      },
      familyMvpEnabled: true,
      theme: 'system',
      baseCurrency: 'GBP',
      refreshConfig: async () => {},
      setRelativeViewEnabled: () => {},
      setBaseCurrency: () => {},
    };
    render(
      <configContext.Provider value={config}>
        <MemoryRouter>
          <Menu onLogout={onLogout} />
        </MemoryRouter>
      </configContext.Provider>
    );
    const preferencesToggle = screen.getByRole('button', {
      name: i18n.t('app.menuCategories.preferences'),
    });
    fireEvent.click(preferencesToggle);
    expect(
      screen.queryByRole('menuitem', { name: i18n.t('app.supportLink') })
    ).not.toBeInTheDocument();
    // Logout remains available in the same category.
    expect(
      screen.getByRole('menuitem', { name: i18n.t('app.logout') })
    ).toBeInTheDocument();
  });

  it('renders logout button when callback provided', async () => {
    const onLogout = vi.fn();
    i18n.changeLanguage('fr');
    const _config: ConfigContextValue = {
      ...configContext._currentValue,
      familyMvpEnabled: false,
    };
    render(
      <configContext.Provider value={_config}>
        <MemoryRouter>
          <Menu onLogout={onLogout} />
        </MemoryRouter>
      </configContext.Provider>
    );
    const settingsToggle = screen.getByRole('button', {
      name: i18n.t('app.menuCategories.preferences'),
    });
    fireEvent.click(settingsToggle);
    const btn = await screen.findByRole('menuitem', { name: 'Déconnexion' });
    fireEvent.click(btn);
    expect(onLogout).toHaveBeenCalled();
    i18n.changeLanguage('en');
  });

  it('applies 44px touch target sizing to dropdown menu items', async () => {
    const onLogout = vi.fn();
    const _config: ConfigContextValue = {
      ...configContext._currentValue,
      familyMvpEnabled: false,
    };
    render(
      <configContext.Provider value={configWithTransactions}>
        <MemoryRouter>
          <Menu onLogout={onLogout} />
        </MemoryRouter>
      </configContext.Provider>
    );

    const dashboardToggle = screen.getByRole('button', {
      name: i18n.t('app.menuCategories.dashboard'),
    });
    fireEvent.click(dashboardToggle);

    const transactionsLink = await screen.findByRole('menuitem', {
      name: i18n.t('app.modes.transactions'),
    });
    const preferencesToggle = screen.getByRole('button', {
      name: i18n.t('app.menuCategories.preferences'),
    });
    fireEvent.click(preferencesToggle);
    const logoutButton = await screen.findByRole('menuitem', {
      name: i18n.t('app.logout'),
    });

    expect(transactionsLink).toHaveClass('min-h-11', 'w-full', 'px-3', 'py-2');
    expect(logoutButton).toHaveClass('min-h-11', 'w-full', 'px-3', 'py-2');
  });

  it('uses at least 8px spacing between adjacent dropdown targets', async () => {
    render(
      <MemoryRouter>
        <Menu />
      </MemoryRouter>
    );

    const dashboardToggle = screen.getByRole('button', {
      name: i18n.t('app.menuCategories.dashboard'),
    });
    fireEvent.click(dashboardToggle);

    const firstMenuItem = await screen.findByRole('menuitem', {
      name: i18n.t('app.modes.owner'),
    });
    const list = firstMenuItem.closest('ul');

    expect(list).toHaveClass('gap-2');
  });

  it('renders enabled menu categories in Family MVP mode (#4641)', () => {
    // Family MVP no longer hides categories: insights/goals tabs are enabled in
    // familyMvpConfig, so their category toggles must appear.
    render(
      <configContext.Provider value={familyMvpConfig}>
        <MemoryRouter>
          <Menu />
        </MemoryRouter>
      </configContext.Provider>
    );

    expect(
      screen.getByRole('button', {
        name: i18n.t('app.menuCategories.insights'),
      })
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: i18n.t('app.menuCategories.goals') })
    ).toBeInTheDocument();
  });

  it('hides menu categories whose tabs are all disabled, even in Family MVP mode', () => {
    // Visibility is driven purely by config: disable every insights/goals tab and
    // those categories disappear regardless of Family MVP being enabled.
    const config: ConfigContextValue = {
      ...familyMvpConfig,
      tabs: {
        ...familyMvpConfig.tabs,
        instrument: false,
        screener: false,
        trading: false,
        watchlist: false,
        rebalance: false,
        scenario: false,
        pension: false,
      },
    };
    render(
      <configContext.Provider value={config}>
        <MemoryRouter>
          <Menu />
        </MemoryRouter>
      </configContext.Provider>
    );

    expect(
      screen.queryByRole('button', {
        name: i18n.t('app.menuCategories.insights'),
      })
    ).toBeNull();
    expect(
      screen.queryByRole('button', { name: i18n.t('app.menuCategories.goals') })
    ).toBeNull();
  });

  it('renders logout via AuthContext when no onLogout prop is passed (#4751)', async () => {
    // Standalone routes (e.g. AlertSettings, PerformanceDiagnostics) mount
    // Menu without threading an onLogout prop through. The control must
    // still work by falling back to the app-wide logout registered in
    // AuthContext, so the button isn't silently missing on those pages.
    const contextLogout = vi.fn();
    render(
      <AuthContext.Provider
        value={{
          user: null,
          setUser: () => {},
          logout: contextLogout,
          setLogout: () => {},
        }}
      >
        <MemoryRouter>
          <Menu />
        </MemoryRouter>
      </AuthContext.Provider>
    );
    const preferencesToggle = screen.getByRole('button', {
      name: i18n.t('app.menuCategories.preferences'),
    });
    fireEvent.click(preferencesToggle);
    const btn = await screen.findByRole('menuitem', {
      name: i18n.t('app.logout'),
    });
    fireEvent.click(btn);
    expect(contextLogout).toHaveBeenCalled();
  });

  it('hides logout when neither onLogout prop nor AuthContext logout is available', () => {
    render(
      <MemoryRouter>
        <Menu />
      </MemoryRouter>
    );
    expect(
      screen.queryByRole('menuitem', { name: i18n.t('app.logout') })
    ).not.toBeInTheDocument();
  });

  it.each([
    ['MVP', true],
    ['non-MVP', false],
  ])(
    'shows the logout button in %s mode (#4490)',
    async (_label, familyMvpEnabled) => {
      // The !familyMvpEnabled guard around the logout button was removed in
      // PR #4482; assert visibility explicitly in both modes so a regression
      // reintroducing that guard is caught directly.
      const onLogout = vi.fn();
      const config: ConfigContextValue = {
        ...configWithTransactions,
        familyMvpEnabled,
      };
      render(
        <configContext.Provider value={config}>
          <MemoryRouter>
            <Menu onLogout={onLogout} />
          </MemoryRouter>
        </configContext.Provider>
      );
      const preferencesToggle = screen.getByRole('button', {
        name: i18n.t('app.menuCategories.preferences'),
      });
      fireEvent.click(preferencesToggle);

      expect(
        await screen.findByRole('menuitem', { name: i18n.t('app.logout') })
      ).toBeInTheDocument();
    }
  );
});
