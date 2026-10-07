import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, beforeEach } from 'vitest';
import i18n from '@/i18n';
import {
  FirstRunHelpBanner,
  FIRST_RUN_HELP_DISMISSED_KEY,
} from '@/components/FirstRunHelpBanner';
import { HELP_PAGES } from '@/lib/helpPages';
import { configContext, type ConfigContextValue } from '@/ConfigContext';

const title = () => i18n.t('firstRunHelp.title', 'New to AllotMint?');

function renderBanner(config?: Partial<ConfigContextValue>) {
  const ui = <FirstRunHelpBanner />;
  return render(
    config ? (
      <configContext.Provider value={config as ConfigContextValue}>
        {ui}
      </configContext.Provider>
    ) : (
      ui
    ),
    { wrapper: MemoryRouter }
  );
}

describe('FirstRunHelpBanner', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it('points a first-time user at Help and the glossary', () => {
    renderBanner();

    expect(screen.getByRole('region', { name: title() })).toBeInTheDocument();
    expect(
      screen.getByRole('link', {
        name: i18n.t('firstRunHelp.openHelp', 'Open Help & Getting Started'),
      })
    ).toHaveAttribute('href', '/help');
    expect(
      screen.getByRole('link', {
        name: i18n.t('help.glossaryLink', 'Open the metrics glossary'),
      })
    ).toHaveAttribute('href', '/metrics-explained');
  });

  it('reuses HELP_PAGES copy rather than its own', () => {
    renderBanner();

    const dashboard = HELP_PAGES.find((entry) => entry.path === '/')!;
    expect(
      screen.getByRole('link', {
        name: i18n.t(dashboard.titleKey, dashboard.titleDefault),
      })
    ).toHaveAttribute('href', '/');
    expect(
      screen.getByText(
        i18n.t(dashboard.descriptionKey, dashboard.descriptionDefault)
      )
    ).toBeInTheDocument();
  });

  it('stays dismissed once dismissed', async () => {
    const { unmount } = renderBanner();

    await userEvent.click(
      screen.getByRole('button', {
        name: i18n.t('firstRunHelp.dismiss', "Got it, don't show again"),
      })
    );
    expect(screen.queryByRole('region', { name: title() })).toBeNull();
    expect(window.localStorage.getItem(FIRST_RUN_HELP_DISMISSED_KEY)).toBe(
      'true'
    );

    unmount();
    renderBanner();
    expect(screen.queryByRole('region', { name: title() })).toBeNull();
  });

  it('is hidden when the Help page is disabled', () => {
    renderBanner({
      tabs: {} as ConfigContextValue['tabs'],
      disabledTabs: ['help'],
    });

    expect(screen.queryByRole('region', { name: title() })).toBeNull();
  });
});
