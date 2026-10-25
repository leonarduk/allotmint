import { lazy, Suspense, useMemo, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { useLocation, useNavigate } from 'react-router-dom';
import { useConfig } from '../ConfigContext';
import { buildChatContext, buildChatPages } from '../utils/chatPages';
import { LanguageSwitcher } from './LanguageSwitcher';
import Menu from './Menu';
import { InstrumentSearchBarToggle } from './InstrumentSearchBar';
import { NotificationsDrawer } from './NotificationsDrawer';
import {
  canDetachChat,
  openChatWindow,
  prefersDetachedChat,
  useChatWindowHost,
} from '../utils/chatWindow';
import UserAvatar from './UserAvatar';

// Icon buttons otherwise inherit the global `button { padding: 0.6em 1.2em }`,
// which at 1.5rem renders each emoji ~91px wide and wraps the header onto a
// second row at phone widths (#7812). Matches the search/language toggles.
const ICON_BUTTON_PADDING = '0.25rem';

// The chat drawer (and the react-markdown/remark-gfm stack its replies render
// with) is fetched on first use rather than in the initial chunk (#7998).
// Hovering/focusing the chat button warms the chunk so opening feels instant.
const loadChatPanel = () => import('./ChatPanel');
const ChatPanel = lazy(() =>
  loadChatPanel().then((module) => ({ default: module.ChatPanel }))
);

const CHAT_WINDOW_BLOCKED =
  'Your browser blocked the chat window. Allow pop-ups for this site to detach the chat.';

interface AppHeaderProps {
  selectedOwner?: string;
  selectedGroup?: string;
  onLogout?: () => void;
  lastRefresh?: string | null;
  /** Extra header content, e.g. an owner selector, rendered between the nav and the refresh badge. */
  children?: ReactNode;
}

/**
 * Shared header row (language switcher, nav, notifications, search, avatar) used by
 * every top-level page so standalone routes match the layout rendered inside App.tsx (#5736).
 */
export default function AppHeader({
  selectedOwner,
  selectedGroup,
  onLogout,
  lastRefresh,
  children,
}: AppHeaderProps) {
  const { t } = useTranslation();
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const [chatNotice, setChatNotice] = useState<string | null>(null);
  // Mounted on first open and kept mounted afterwards, so the drawer keeps its
  // in-progress state (draft, pending reply) across close/reopen as before.
  const [chatMounted, setChatMounted] = useState(false);
  if (chatOpen && !chatMounted) setChatMounted(true);
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const { tabs, disabledTabs } = useConfig();
  const chatPages = useMemo(
    () => buildChatPages(tabs, disabledTabs, (mode) => t(`app.modes.${mode}`)),
    [tabs, disabledTabs, t]
  );
  const chatContext = useMemo(
    () => buildChatContext(pathname, { owner: selectedOwner, group: selectedGroup }),
    [pathname, selectedOwner, selectedGroup]
  );
  // While detached the chat lives in its own window (#9025): pages it opens
  // load here and it stays open; Reattach brings the drawer back.
  const chatDetached = useChatWindowHost({
    pages: chatPages,
    context: chatContext,
    onNavigate: navigate,
    onReattach: () => setChatOpen(true),
  });

  // Opens the chat window; when the browser blocks it, the drawer instead.
  const detachChat = () => {
    if (openChatWindow()) {
      setChatOpen(false);
      setChatNotice(null);
    } else {
      setChatOpen(true);
      setChatNotice(CHAT_WINDOW_BLOCKED);
    }
  };

  const openChat = () => {
    if (chatDetached || (prefersDetachedChat() && canDetachChat())) detachChat();
    else setChatOpen(true);
  };

  return (
    <>
      <div
        className="flex-wrap-row"
        style={{
          alignItems: 'center',
          gap: '0.5rem',
          margin: '1rem 0',
        }}
      >
        <LanguageSwitcher />
        <Menu
          selectedOwner={selectedOwner}
          selectedGroup={selectedGroup}
          onLogout={onLogout}
          style={{ margin: 0 }}
        />
        {children}
        {lastRefresh && (
          <span
            style={{
              background: '#eee',
              borderRadius: '1rem',
              padding: '0.25rem 0.5rem',
              fontSize: '0.75rem',
            }}
            title={t('app.last') ?? undefined}
          >
            {new Date(lastRefresh).toLocaleString()}
          </span>
        )}
        <InstrumentSearchBarToggle />
        <button
          aria-label={t('appHeader.notifications')}
          onClick={() => setNotificationsOpen(true)}
          style={{
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            fontSize: '1.5rem',
            padding: ICON_BUTTON_PADDING,
          }}
        >
          🔔
        </button>
        <button
          aria-label={t('appHeader.chat')}
          aria-pressed={chatDetached || undefined}
          title={chatDetached ? t('appHeader.chatDetached') : undefined}
          onClick={openChat}
          onMouseEnter={() => void loadChatPanel()}
          onFocus={() => void loadChatPanel()}
          style={{
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            fontSize: '1.5rem',
            padding: ICON_BUTTON_PADDING,
            borderRadius: '0.25rem',
            outline: chatDetached ? '2px solid currentColor' : undefined,
          }}
        >
          💬
        </button>
        <UserAvatar />
      </div>
      <NotificationsDrawer
        open={notificationsOpen}
        onClose={() => setNotificationsOpen(false)}
      />
      {chatMounted && (
        <Suspense fallback={null}>
          <ChatPanel
            open={chatOpen && !chatDetached}
            onClose={() => {
              setChatOpen(false);
              setChatNotice(null);
            }}
            pages={chatPages}
            context={chatContext}
            onDetach={canDetachChat() ? detachChat : undefined}
            notice={chatNotice}
            onNavigate={(path) => {
              // Close the drawer so the page the user asked for is visible; the
              // conversation is kept for when they reopen it.
              setChatOpen(false);
              navigate(path);
            }}
          />
        </Suspense>
      )}
    </>
  );
}
