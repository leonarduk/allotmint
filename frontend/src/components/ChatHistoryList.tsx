import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import * as api from "../api";
import type { SavedChatSummary } from "../api";
import { saveCurrentChat } from "../utils/chatSync";
import { CHAT_INPUT_STYLE } from "./chatInputStyle";

interface Props {
  /** Opens a chat: "current" just returns to it; any other id is an archived chat. */
  onOpen: (id: string) => void;
  /** Disables the actions while the panel is busy (e.g. opening a chat). */
  busy?: boolean;
}

const CURRENT = "current";

function formatWhen(iso: string | null): string {
  if (!iso) return "";
  const date = new Date(iso);
  return Number.isNaN(date.getTime())
    ? ""
    : date.toLocaleString(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
      });
}

// The saved chats (#8870): the current one and those put away by "New chat",
// newest first, each of which can be opened, renamed or deleted.
export function ChatHistoryList({ onOpen, busy = false }: Props) {
  const { t } = useTranslation();
  const [chats, setChats] = useState<SavedChatSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [renaming, setRenaming] = useState<{
    id: string;
    draft: string;
  } | null>(null);
  const [confirmingDelete, setConfirmingDelete] = useState<string | null>(null);
  const [working, setWorking] = useState(false);

  const reload = useCallback(async () => {
    try {
      setChats((await api.listSavedChats()).chats);
      setError(null);
    } catch (e) {
      console.warn("Saved chats could not be loaded", e);
      setError(t("chatHistory.loadFailed"));
    }
  }, [t]);

  useEffect(() => {
    // Save this tab's chat first, so the list shows it as it is now.
    void saveCurrentChat()
      .catch((e) => console.warn("Chat history was not saved", e))
      .then(reload);
  }, [reload]);

  const run = async (action: () => Promise<void>, failure: string) => {
    setWorking(true);
    setError(null);
    try {
      await action();
      await reload();
    } catch (e) {
      console.warn(failure, e);
      setError(failure);
    } finally {
      setWorking(false);
    }
  };

  const saveRename = () => {
    if (!renaming) return;
    const { id, draft } = renaming;
    setRenaming(null);
    void run(async () => {
      if (id === CURRENT) await saveCurrentChat();
      await api.renameSavedChat(id, draft.trim());
    }, t("chatHistory.renameFailed"));
  };

  const remove = (id: string) => {
    setConfirmingDelete(null);
    void run(() => api.deleteSavedChat(id), t("chatHistory.deleteFailed"));
  };

  const disabled = busy || working;

  return (
    <div>
      {error && <div role="alert">{error}</div>}
      {chats === null && !error && <div role="status">{t("chatHistory.loading")}</div>}
      {chats?.length === 0 && (
        <div style={{ color: "var(--drawer-muted-color)" }}>
          {t("chatHistory.empty")}
        </div>
      )}
      <ul aria-label={t("chatHistory.savedChats")} style={{ listStyle: "none", padding: 0, margin: 0 }}>
        {chats?.map((chat) => (
          <li
            key={chat.id}
            style={{
              padding: "0.5rem 0",
              borderBottom: "1px solid var(--drawer-border-color)",
            }}
          >
            {renaming?.id === chat.id ? (
              <div style={{ display: "flex", gap: "0.5rem" }}>
                <input
                  aria-label={t("chatHistory.chatName")}
                  value={renaming.draft}
                  maxLength={120}
                  autoFocus
                  onChange={(e) => setRenaming({ id: chat.id, draft: e.target.value })}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") saveRename();
                    if (e.key === "Escape") setRenaming(null);
                  }}
                  style={{ ...CHAT_INPUT_STYLE, flex: 1 }}
                />
                <button onClick={saveRename}>{t("chatHistory.save")}</button>
                <button onClick={() => setRenaming(null)}>{t("chatHistory.cancel")}</button>
              </div>
            ) : (
              <>
                <button
                  onClick={() => onOpen(chat.id)}
                  disabled={disabled}
                  title={chat.id === CURRENT ? t("chatHistory.backToThisChat") : t("chatHistory.openThisChat")}
                  style={{
                    background: "none",
                    border: "none",
                    padding: 0,
                    color: "inherit",
                    cursor: "pointer",
                    textAlign: "left",
                    fontWeight: 600,
                    fontStyle: chat.named ? "normal" : "italic",
                  }}
                >
                  {chat.title}
                </button>
                <div
                  style={{
                    color: "var(--drawer-muted-color)",
                    fontSize: "0.85em",
                  }}
                >
                  {chat.id === CURRENT && <strong>{t("chatHistory.current")} · </strong>}
                  {t("chatHistory.messageCount", { count: chat.messages })}
                  {chat.updated_at && ` · ${formatWhen(chat.updated_at)}`}
                </div>
                {confirmingDelete === chat.id ? (
                  <div
                    role="group"
                    aria-label={t("chatHistory.confirmDeleting", { title: chat.title })}
                    style={{ display: "flex", gap: "0.5rem" }}
                  >
                    <span style={{ flex: 1 }}>{t("chatHistory.deletePrompt")}</span>
                    <button onClick={() => remove(chat.id)}>{t("chatHistory.delete")}</button>
                    <button onClick={() => setConfirmingDelete(null)}>{t("chatHistory.cancel")}</button>
                  </div>
                ) : (
                  <div
                    style={{
                      display: "flex",
                      gap: "0.5rem",
                      marginTop: "0.25rem",
                    }}
                  >
                    <button
                      onClick={() =>
                        setRenaming({
                          id: chat.id,
                          draft: chat.named ? chat.title : "",
                        })
                      }
                      disabled={disabled}
                      aria-label={t("chatHistory.renameTitle", { title: chat.title })}
                    >
                      {t("chatHistory.rename")}
                    </button>
                    {chat.id !== CURRENT && (
                      <button
                        onClick={() => setConfirmingDelete(chat.id)}
                        disabled={disabled}
                        aria-label={t("chatHistory.deleteTitle", { title: chat.title })}
                      >
                        {t("chatHistory.delete")}
                      </button>
                    )}
                  </div>
                )}
              </>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

export default ChatHistoryList;
