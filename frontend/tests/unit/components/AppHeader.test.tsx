import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import i18n from '@/i18n';
import AppHeader from '@/components/AppHeader';
import { configContext, type ConfigContextValue } from '@/ConfigContext';

vi.mock('@/components/Menu', () => ({ default: () => <nav /> }));
vi.mock('@/components/UserAvatar', () => ({ default: () => <span /> }));
vi.mock('@/components/LanguageSwitcher', () => ({
  LanguageSwitcher: () => <span />,
}));
vi.mock('@/components/InstrumentSearchBar', () => ({
  InstrumentSearchBarToggle: () => <span />,
}));
vi.mock('@/components/NotificationsDrawer', () => ({
  NotificationsDrawer: () => null,
}));
vi.mock('@/components/ChatPanel', () => ({ ChatPanel: () => null }));

const config: ConfigContextValue = {
  configLoaded: true,
  relativeViewEnabled: false,
  familyMvpEnabled: false,
  disabledTabs: [],
  tabs: { group: true } as ConfigContextValue['tabs'],
  theme: 'dark',
  reportingCurrency: 'GBP',
  refreshConfig: async () => {},
  setRelativeViewEnabled: () => {},
};

describe('AppHeader', () => {
  // The global `button { padding: 0.6em 1.2em }` made each 1.5rem emoji
  // button ~91px wide, wrapping the header onto two rows at 390px (#7812).
  it('gives the notification and chat icon buttons compact padding', () => {
    render(
      <configContext.Provider value={config}>
        <MemoryRouter>
          <AppHeader />
        </MemoryRouter>
      </configContext.Provider>
    );

    for (const key of ['appHeader.notifications', 'appHeader.chat']) {
      const button = screen.getByRole('button', { name: i18n.t(key) });
      expect(button.style.padding).toBe('0.25rem');
    }
  });
});
