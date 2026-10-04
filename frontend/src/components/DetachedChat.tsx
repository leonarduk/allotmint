import { useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useConfig } from '../ConfigContext';
import { buildChatPages } from '../utils/chatPages';
import { useDetachedChatWindow } from '../utils/chatWindow';
import { ChatPanel } from './ChatPanel';

/**
 * The chat on its own, in the window AppHeader's Detach opens (#9025). Pages
 * the assistant opens load in the main window, and the main window's page is
 * the context sent with each turn.
 */
export default function DetachedChat() {
  const { t } = useTranslation();
  const { tabs, disabledTabs } = useConfig();
  const pages = useMemo(
    () => buildChatPages(tabs, disabledTabs, (mode) => t(`app.modes.${mode}`)),
    [tabs, disabledTabs, t]
  );
  const { context, linked, navigate, reattach } = useDetachedChatWindow();

  useEffect(() => {
    document.title = 'AllotMint chat';
  }, []);

  return (
    <ChatPanel
      open
      variant="window"
      onClose={() => window.close()}
      pages={pages}
      context={context}
      onNavigate={linked ? navigate : undefined}
      onReattach={linked ? reattach : undefined}
    />
  );
}
