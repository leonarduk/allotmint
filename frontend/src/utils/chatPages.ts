import type { TabsConfig } from '../ConfigContext';
import type { ChatPage } from '../api';
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
