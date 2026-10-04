import { useCallback, useEffect, useState } from "react";
import * as api from "../api";
import type { SavedChatSummary } from "../api";
import { saveCurrentChat } from "../utils/chatSync";

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
      setError("Couldn't load your saved chats. Please try again.");
    }
  }, []);

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
    }, "Couldn't rename that chat. Please try again.");
  };

  const remove = (id: string) => {
    setConfirmingDelete(null);
    void run(() => api.deleteSavedChat(id), "Couldn't delete that chat. Please try again.");
  };

  const disabled = busy || working;

  return (
    <div>
      {error && <div role="alert">{error}</div>}
      {chats === null && !error && <div role="status">Loading saved chats…</div>}
      {chats?.length === 0 && (
        <div style={{ color: "var(--drawer-muted-color)" }}>
          No saved chats yet. Each chat is saved as you go; New chat keeps the old one here.
        </div>
      )}
      <ul aria-label="Saved chats" style={{ listStyle: "none", padding: 0, margin: 0 }}>
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
                  aria-label="Chat name"
                  value={renaming.draft}
                  maxLength={120}
                  autoFocus
                  onChange={(e) => setRenaming({ id: chat.id, draft: e.target.value })}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") saveRename();
                    if (e.key === "Escape") setRenaming(null);
                  }}
                  style={{ flex: 1 }}
                />
                <button onClick={saveRename}>Save</button>
                <button onClick={() => setRenaming(null)}>Cancel</button>
              </div>
            ) : (
              <>
                <button
                  onClick={() => onOpen(chat.id)}
                  disabled={disabled}
                  title={chat.id === CURRENT ? "Back to this chat" : "Open this chat"}
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
                  {chat.id === CURRENT && <strong>Current · </strong>}
                  {chat.messages} message{chat.messages === 1 ? "" : "s"}
                  {chat.updated_at && ` · ${formatWhen(chat.updated_at)}`}
                </div>
                {confirmingDelete === chat.id ? (
                  <div
                    role="group"
                    aria-label={`Confirm deleting ${chat.title}`}
                    style={{ display: "flex", gap: "0.5rem" }}
                  >
                    <span style={{ flex: 1 }}>Delete this chat? This can't be undone.</span>
                    <button onClick={() => remove(chat.id)}>Delete</button>
                    <button onClick={() => setConfirmingDelete(null)}>Cancel</button>
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
                      aria-label={`Rename ${chat.title}`}
                    >
                      Rename
                    </button>
                    {chat.id !== CURRENT && (
                      <button
                        onClick={() => setConfirmingDelete(chat.id)}
                        disabled={disabled}
                        aria-label={`Delete ${chat.title}`}
                      >
                        Delete
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
