import type { TabsConfig } from '../ConfigContext';
import type { ChatContext, ChatPage } from '../api';
import type { Mode } from '../modes';
import { buildPathForMode, getMenuEntries } from '../pageManifest';

// The menu sends Transactions to /input (the holdings input form). Asked to
// "go to the transactions page", the chat should open the transactions list
// itself, and offer /input as its own page.
const CHAT_PATH_OVERRIDES: Partial<Record<Mode, string>> = {
  transactions: '/transactions',
};

/**
 * Pages the chat may navigate to: every menu entry enabled for this user,
 * at its default path. Sent with each chat turn; the backend only lets the
 * model open one of these (backend/chat/local_tools.py).
 */
export function buildChatPages(
  tabs: TabsConfig,
  disabledTabs: readonly string[] | undefined,
  labelFor: (mode: Mode) => string
): ChatPage[] {
  const pages: ChatPage[] = [];
  for (const section of ['user', 'support'] as const) {
    for (const entry of getMenuEntries(section)) {
      if (tabs[entry.mode] !== true || disabledTabs?.includes(entry.mode)) {
        continue;
      }
      pages.push({
        path: CHAT_PATH_OVERRIDES[entry.mode] ?? buildPathForMode(entry.mode),
        label: labelFor(entry.mode),
      });
      if (entry.mode === 'transactions') {
        pages.push({ path: '/input', label: 'Account + holdings input' });
      }
    }
  }
  return pages;
}

// Instrument pages live at /research/:ticker.
const RESEARCH_PATH = /^\/research\/([^/]+)\/?$/;

// Mirrors ChatContextIn's owner/group pattern (backend/routes/chat.py): a slug
// it would reject is left out rather than failing the whole turn with a 422.
const SCOPE_SLUG = /^[A-Za-z0-9._-]{1,64}$/;

/** The owner or group selected in the app, if any. */
export type ChatScope = { owner?: string | null; group?: string | null };

/**
 * The page the user is on, sent with each chat turn (backend/chat/local_tools.py),
 * plus the owner -- or, with none selected, the group -- in view (#10813).
 */
export function buildChatContext(pathname: string, scope: ChatScope = {}): ChatContext {
  const context: ChatContext = { path: pathname };
  const match = RESEARCH_PATH.exec(pathname);
  if (match) {
    try {
      context.ticker = decodeURIComponent(match[1]);
    } catch {
      // A malformed escape: leave the ticker out.
    }
  }
  const owner = scope.owner?.trim();
  const group = scope.group?.trim();
  if (owner) {
    if (SCOPE_SLUG.test(owner)) context.owner = owner;
  } else if (group && SCOPE_SLUG.test(group)) {
    context.group = group;
  }
  return context;
}
