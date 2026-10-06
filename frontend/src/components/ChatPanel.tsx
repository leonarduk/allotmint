import { useEffect, useRef, useState, type CSSProperties } from "react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import * as api from "../api";
import type { ChatContext, ChatFile, ChatMessage, ChatPage } from "../api";
import {
  addChatVersion,
  appendChatMessage,
  endChatPathAt,
  restoreChat,
  selectChatVersion,
  snapshotChat,
  useChatMessages,
  useChatPath,
} from "../utils/chatConversation";
import {
  deleteSavedChatHistory,
  ensureChatLoaded,
  openSavedChat,
  setChatReplyPending,
  startNewSavedChat,
  useChatSaveFailed,
} from "../utils/chatSync";
import { isDemoSession } from "../demoAuth";
import { ChatHistoryList } from "./ChatHistoryList";
import { ChatMessageItem } from "./ChatMessageItem";
import { CHAT_INPUT_STYLE } from "./chatInputStyle";

interface Props {
  open: boolean;
  onClose: () => void;
  /** Pages the assistant may open for the user. */
  pages?: ChatPage[];
  /** The page the user is on, sent with each turn. */
  context?: ChatContext;
  /** Called with a page's path when the assistant opens it. */
  onNavigate?: (path: string) => void;
  /** "window" fills a detached chat window (#9025); the default is a drawer over the page. */
  variant?: "drawer" | "window";
  /** Offered in the drawer: moves the chat into its own window. */
  onDetach?: () => void;
  /** Offered in a detached window: moves the chat back into the main window. */
  onReattach?: () => void;
  /** A message about the panel itself, e.g. that the chat window was blocked. */
  notice?: string | null;
}

const DRAWER_STYLE: CSSProperties = {
  position: "fixed",
  top: 0,
  right: 0,
  width: "min(560px, 100vw)",
  height: "100%",
  borderLeft: "1px solid var(--drawer-border-color)",
  boxShadow: "-2px 0 5px rgba(0,0,0,0.3)",
  zIndex: 1000,
};

// Fixed rather than 100vh, so the body's margin cannot add a scrollbar.
const WINDOW_STYLE: CSSProperties = {
  position: "fixed",
  inset: 0,
};

// Map a failed send to fixed wording rather than echoing the backend's error
// text (#7721; #7131 precedent). The `code` POST /chat sends with a 502/503
// (backend/routes/chat.py) names the piece that failed and wins; otherwise
// the HTTP status decides. Only a request that got no response at all is
// "Cannot reach server".
const CHAT_CODE_MESSAGES: Record<string, string> = {
  chat_not_configured: "chatPanel.errors.chatNotConfigured",
  mcp_unreachable: "chatPanel.errors.mcpUnreachable",
  llm_unreachable: "chatPanel.errors.llmUnreachable",
  aws_error: "chatPanel.errors.awsError",
};

const CHAT_STATUS_MESSAGES: Record<number, string> = {
  400: "chatPanel.errors.status400",
  401: "chatPanel.errors.status401",
  429: "chatPanel.errors.status429",
  502: "chatPanel.errors.status502",
  503: "chatPanel.errors.status503",
  504: "chatPanel.errors.status504",
};

function chatErrorMessage(e: unknown, t: TFunction): string {
  const err = e as { status?: unknown; timeout?: unknown; code?: unknown } | null;
  if (typeof err?.code === "string" && Object.hasOwn(CHAT_CODE_MESSAGES, err.code)) {
    return t(CHAT_CODE_MESSAGES[err.code]);
  }
  if (err?.timeout) return t(CHAT_STATUS_MESSAGES[504]);
  if (typeof err?.status === "number") {
    return t(CHAT_STATUS_MESSAGES[err.status] ?? "chatPanel.errors.serverError");
  }
  return t("chatPanel.errors.cannotReachServer");
}

export function ChatPanel({
  open,
  onClose,
  pages = [],
  context,
  onNavigate,
  variant = "drawer",
  onDetach,
  onReattach,
  notice,
}: Props) {
  const { t } = useTranslation();
  const messages = useChatMessages();
  const path = useChatPath();
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<{ index: number; draft: string } | null>(null);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  // "history" lists the saved chats in place of the conversation.
  const [view, setView] = useState<"chat" | "history">("chat");
  const [opening, setOpening] = useState(false);
  // Files the assistant exported, by the id of the reply they came with. Kept
  // for this session only: the saved conversation holds just the text (#9039).
  const [files, setFiles] = useState<Record<string, ChatFile[]>>({});
  const saveFailed = useChatSaveFailed();
  const bottomRef = useRef<HTMLDivElement>(null);

  // Picks up the conversation saved on the server (#8870); a failure leaves
  // the local one in place and shows the "Not saved" hint.
  useEffect(() => {
    if (open) void ensureChatLoaded();
  }, [open]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView?.({ block: "end" });
  }, [messages, sending]);

  if (!open) return null;

  // Posts `text` as the next user turn after `history`. `place` puts that turn
  // in the conversation; the reply is appended after it. On failure the
  // conversation is restored exactly as it was before `place`, so no
  // unanswered turn is left behind: history ending in two consecutive "user"
  // turns is rejected by the backend with a 400 (#7897).
  const submit = async (
    text: string,
    history: ChatMessage[],
    place: () => void,
    onFail?: () => void,
  ) => {
    const before = snapshotChat();
    // Not saved until the reply is in: on failure it is rolled back anyway.
    setChatReplyPending(true);
    place();
    setSending(true);
    setError(null);
    try {
      const { reply, navigate_to, files: replyFiles } = await api.postChat(text, history, pages, context);
      const replyId = appendChatMessage({ role: "assistant", content: reply });
      if (replyFiles?.length) setFiles((prev) => ({ ...prev, [replyId]: replyFiles }));
      // Only follow a path that was offered: the backend enforces this too.
      if (navigate_to && onNavigate && pages.some((page) => page.path === navigate_to)) {
        onNavigate(navigate_to);
      }
    } catch (e) {
      restoreChat(before);
      onFail?.();
      setError(chatErrorMessage(e, t));
    } finally {
      setSending(false);
      setChatReplyPending(false);
    }
  };

  const send = async () => {
    const text = input.trim();
    if (!text || sending) return;

    setInput("");
    // Hand the unanswered message's text back for a retry.
    await submit(
      text,
      messages,
      () => appendChatMessage({ role: "user", content: text }),
      () => setInput(text),
    );
  };

  // Adds the edited text as a new version of the message and regenerates from
  // there, sending only the turns before it as history. The old version keeps
  // its later turns, reachable through the version control (#8590, #8842).
  const saveEdit = async () => {
    if (!editing || sending) return;
    const { index } = editing;
    const node = path[index];
    const text = editing.draft.trim();
    if (!node || !text) return;
    setEditing(null);
    if (text === node.content) return;

    // On failure reopen the edit box with the edited text, so it can be retried.
    await submit(
      text,
      messages.slice(0, index),
      () => addChatVersion(node.id, { role: "user", content: text }),
      () => setEditing({ index, draft: text }),
    );
  };

  // Asks again for the reply at `index` without changing the question. The
  // new reply becomes another version of it; the old one and its later turns
  // are kept. A failure restores the old reply as the active one (#8820, #8842).
  const regenerate = async (index: number) => {
    const prompt = path[index - 1];
    if (sending || prompt?.role !== "user") return;

    setEditing(null);
    await submit(prompt.content, messages.slice(0, index - 1), () => endChatPathAt(prompt.id));
  };

  // Deletes the saved history (this conversation and every archived one). On
  // failure the conversation is kept and the error shown.
  const deleteHistory = async () => {
    setDeleting(true);
    setError(null);
    try {
      await deleteSavedChatHistory();
      setInput("");
      setEditing(null);
    } catch {
      setError(t("chatPanel.errors.deleteHistoryFailed"));
    } finally {
      setDeleting(false);
      setConfirmingDelete(false);
    }
  };

  // Opens a saved chat from the history list; the current one is archived.
  const openChat = async (id: string) => {
    setError(null);
    if (id !== "current") {
      setOpening(true);
      try {
        await openSavedChat(id);
      } catch (e) {
        console.warn("Saved chat could not be opened", e);
        setError(t("chatPanel.errors.openFailed"));
        return;
      } finally {
        setOpening(false);
      }
      setInput("");
      setEditing(null);
    }
    setView("chat");
  };

  const selectVersion = (id: string, offset: number) => {
    if (sending) return;
    setEditing(null);
    selectChatVersion(id, offset);
  };

  const isWindow = variant === "window";

  return (
    <>
      {!isWindow && (
        <div
          onClick={onClose}
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            width: "100%",
            height: "100%",
            background: "rgba(0,0,0,0.3)",
            zIndex: 999,
          }}
        />
      )}
      <div
        role={isWindow ? "region" : "dialog"}
        aria-label={t("chatPanel.chat")}
        style={{
          ...(isWindow ? WINDOW_STYLE : DRAWER_STYLE),
          boxSizing: "border-box",
          background: "var(--drawer-bg)",
          color: "var(--drawer-color)",
          padding: "1rem",
          display: "flex",
          flexDirection: "column",
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: "1rem",
          }}
        >
          <div style={{ display: "flex", alignItems: "baseline", gap: "0.5rem" }}>
            <strong>{t("chatPanel.chat")}</strong>
            {saveFailed && (
              <span
                title={t("chatPanel.notSavedHint")}
                style={{ color: "var(--drawer-muted-color)", fontSize: "0.85em" }}
              >
                {t("chatPanel.notSaved")}
              </span>
            )}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            {!isDemoSession() && (
              <button
                onClick={() => {
                  setError(null);
                  setView(view === "history" ? "chat" : "history");
                }}
                disabled={sending || opening}
                aria-pressed={view === "history"}
              >
                {view === "history" ? t("chatPanel.backToChat") : t("chatPanel.history")}
              </button>
            )}
            {!isDemoSession() && (
              <button
                onClick={() => setConfirmingDelete(true)}
                disabled={sending || deleting || confirmingDelete}
              >
                {t("chatPanel.deleteHistory")}
              </button>
            )}
            <button
              onClick={() => {
                startNewSavedChat();
                setInput("");
                setEditing(null);
                setError(null);
                setView("chat");
              }}
              disabled={sending || opening || messages.length === 0}
            >
              {t("chatPanel.newChat")}
            </button>
            {onDetach && (
              <button onClick={onDetach} title={t("chatPanel.detachTitle")}>
                {t("chatPanel.detach")}
              </button>
            )}
            {onReattach && (
              <button onClick={onReattach} title={t("chatPanel.reattachTitle")}>
                {t("chatPanel.reattach")}
              </button>
            )}
            {!isWindow && (
              <button
                onClick={onClose}
                aria-label={t("chatPanel.close")}
                style={{
                  background: "none",
                  border: "none",
                  fontSize: "1.2rem",
                  cursor: "pointer",
                }}
              >
                ×
              </button>
            )}
          </div>
        </div>
        {notice && (
          <div role="alert" style={{ marginBottom: "1rem" }}>
            {notice}
          </div>
        )}
        {confirmingDelete && (
          <div
            role="group"
            aria-label={t("chatPanel.confirmDeleteHistory")}
            style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "0.5rem", marginBottom: "1rem" }}
          >
            <span style={{ flex: "1 1 12rem" }}>
              {t("chatPanel.deleteHistoryPrompt")}
            </span>
            <button onClick={() => void deleteHistory()} disabled={deleting}>
              {t("chatPanel.delete")}
            </button>
            <button onClick={() => setConfirmingDelete(false)} disabled={deleting}>
              {t("chatPanel.cancel")}
            </button>
          </div>
        )}
        {view === "history" ? (
          <div style={{ flex: 1, overflowY: "auto" }}>
            {error && <div role="alert">{error}</div>}
            <ChatHistoryList onOpen={(id) => void openChat(id)} busy={opening} />
          </div>
        ) : (
          <>
            <div style={{ flex: 1, overflowY: "auto", marginBottom: "1rem" }}>
              {messages.length === 0 && (
                <div style={{ color: "var(--drawer-muted-color)" }}>
                  {t("chatPanel.emptyPrompt")}
                </div>
              )}
              <ul
                style={{
                  listStyle: "none",
                  padding: 0,
                  margin: 0,
                  display: "flex",
                  flexDirection: "column",
                  gap: "0.75rem",
                }}
              >
                {path.map((m, i) => (
                  <ChatMessageItem
                    key={m.id}
                    message={m}
                    files={files[m.id]}
                    busy={sending}
                    version={
                      m.versionCount > 1
                        ? {
                            current: m.version,
                            count: m.versionCount,
                            onSelect: (offset) => selectVersion(m.id, offset),
                          }
                        : undefined
                    }
                    onEdit={
                      m.role === "user" ? () => setEditing({ index: i, draft: m.content }) : undefined
                    }
                    onRegenerate={
                      m.role === "assistant" && path[i - 1]?.role === "user"
                        ? () => void regenerate(i)
                        : undefined
                    }
                    editing={
                      editing?.index === i
                        ? {
                            draft: editing.draft,
                            onChange: (draft) => setEditing({ index: i, draft }),
                            onSave: () => void saveEdit(),
                            onCancel: () => setEditing(null),
                          }
                        : undefined
                    }
                  />
                ))}
              </ul>
              {sending && (
                <div role="status" style={{ color: "var(--drawer-muted-color)", marginTop: "0.75rem" }}>
                  {t("chatPanel.thinking")}
                </div>
              )}
              {error && <div role="alert">{error}</div>}
              <div ref={bottomRef} />
            </div>
            <div style={{ display: "flex", gap: "0.5rem" }}>
              <input
                aria-label={t("chatPanel.messageInput")}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") void send();
                }}
                style={{ ...CHAT_INPUT_STYLE, flex: 1 }}
                disabled={sending}
              />
              <button onClick={() => void send()} disabled={sending || !input.trim()}>
                {t("chatPanel.send")}
              </button>
            </div>
          </>
        )}
      </div>
    </>
  );
}

export default ChatPanel;
