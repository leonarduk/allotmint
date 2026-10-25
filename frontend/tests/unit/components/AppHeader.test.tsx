import { fireEvent, render, screen } from '@testing-library/react';
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
vi.mock('@/components/ChatPanel', () => ({
  ChatPanel: ({ open, onClose }: { open: boolean; onClose: () => void }) => (
    <div data-testid="chat-panel" data-open={String(open)}>
      <button onClick={onClose}>close chat</button>
    </div>
  ),
}));

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

function renderHeader() {
  return render(
    <configContext.Provider value={config}>
      <MemoryRouter>
        <AppHeader />
      </MemoryRouter>
    </configContext.Provider>
  );
}

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

  // The chat drawer pulls in react-markdown/remark-gfm, so it is lazy-loaded
  // on first open instead of shipping in the initial chunk (#7998).
  it('does not mount the chat drawer until the chat is first opened', async () => {
    renderHeader();
    expect(screen.queryByTestId('chat-panel')).toBeNull();

    fireEvent.click(
      screen.getByRole('button', { name: i18n.t('appHeader.chat') })
    );
    const panel = await screen.findByTestId('chat-panel');
    expect(panel).toHaveAttribute('data-open', 'true');
  });

  it('keeps the chat drawer mounted (closed) after it is closed', async () => {
    renderHeader();
    fireEvent.click(
      screen.getByRole('button', { name: i18n.t('appHeader.chat') })
    );
    fireEvent.click(await screen.findByRole('button', { name: 'close chat' }));

    expect(screen.getByTestId('chat-panel')).toHaveAttribute(
      'data-open',
      'false'
    );
  });
});
