import { useEffect, useRef, useState } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { Check, ChevronLeft, ChevronRight, Copy, Download, Pencil, RefreshCw } from "lucide-react";
import type { ChatFile, ChatMessage } from "../api";
import { downloadChatFile } from "../lib/chatFileDownload";
import { CHAT_INPUT_STYLE } from "./chatInputStyle";

// Assistant replies are Markdown (headings, bold, GFM tables). Raw HTML is not
// rendered (react-markdown's default), so model output cannot inject markup.
const markdownComponents: Components = {
  table: ({ children }) => (
    <div className="chat-markdown-table">
      <table>{children}</table>
    </div>
  ),
  a: ({ children, href }) => (
    <a href={href} target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  ),
};

type CopyState = "idle" | "copied" | "failed";

const COPY_FEEDBACK_MS = 2000;

// Copies the raw message text: for an assistant reply that is its Markdown
// source, not the rendered HTML (#8590).
function CopyButton({ text }: { text: string }) {
  const [state, setState] = useState<CopyState>("idle");

  useEffect(() => {
    if (state === "idle") return;
    const timer = setTimeout(() => setState("idle"), COPY_FEEDBACK_MS);
    return () => clearTimeout(timer);
  }, [state]);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setState("copied");
    } catch {
      // Clipboard is unavailable (insecure context or permission denied):
      // say so rather than pretending it worked.
      setState("failed");
    }
  };

  return (
    <>
      <span className="chat-message-copy-status" aria-live="polite">
        {state === "copied" ? "Copied" : state === "failed" ? "Copy failed" : ""}
      </span>
      <button
        type="button"
        className="chat-message-action"
        aria-label="Copy message"
        title="Copy"
        onClick={() => void copy()}
      >
        {state === "copied" ? <Check size={14} aria-hidden /> : <Copy size={14} aria-hidden />}
      </button>
    </>
  );
}

interface EditFormProps {
  draft: string;
  disabled: boolean;
  onChange: (draft: string) => void;
  onSave: () => void;
  onCancel: () => void;
}

function EditForm({ draft, disabled, onChange, onSave, onCancel }: EditFormProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Focus with the caret at the end (autoFocus puts it at the start), so
  // typing adds to the message rather than prefixing it.
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.focus();
    el.setSelectionRange(el.value.length, el.value.length);
  }, []);

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSave();
      }}
      style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}
    >
      <textarea
        aria-label="Edited message"
        ref={textareaRef}
        value={draft}
        rows={Math.min(8, Math.max(2, draft.split("\n").length))}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Escape") {
            e.preventDefault();
            onCancel();
          } else if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            onSave();
          }
        }}
        style={{
          ...CHAT_INPUT_STYLE,
          width: "100%",
          minWidth: "16rem",
          resize: "vertical",
        }}
      />
      <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.5rem" }}>
        <button type="button" onClick={onCancel}>
          Cancel
        </button>
        <button type="submit" disabled={disabled || !draft.trim()}>
          Save &amp; regenerate
        </button>
      </div>
    </form>
  );
}

export interface ChatMessageVersion {
  /** 1-based position of this version. */
  current: number;
  count: number;
  /** Switches to the version `offset` steps away (-1 previous, +1 next). */
  onSelect: (offset: number) => void;
}

// "‹ 2 / 3 ›" switcher for a message that has been edited or regenerated
// (#8842). Always visible, unlike the hover actions, so the user can see that
// other versions exist.
function VersionSwitcher({ version, busy }: { version: ChatMessageVersion; busy: boolean }) {
  const { current, count, onSelect } = version;
  return (
    <div className="chat-message-versions" role="group" aria-label="Message versions">
      <button
        type="button"
        className="chat-message-action"
        aria-label="Previous version"
        onClick={() => onSelect(-1)}
        disabled={busy || current <= 1}
      >
        <ChevronLeft size={14} aria-hidden />
      </button>
      <span aria-live="polite" title={`Version ${current} of ${count}`}>
        {current} / {count}
      </span>
      <button
        type="button"
        className="chat-message-action"
        aria-label="Next version"
        onClick={() => onSelect(1)}
        disabled={busy || current >= count}
      >
        <ChevronRight size={14} aria-hidden />
      </button>
    </div>
  );
}

// Download buttons for the files the assistant exported with this reply (#9039).
function ChatFiles({ files }: { files: ChatFile[] }) {
  return (
    <ul className="chat-message-files" aria-label="Exported files" style={{ listStyle: "none", padding: 0, margin: "0.5rem 0 0" }}>
      {files.map((file, i) => (
        <li key={`${i}-${file.filename}`}>
          <button
            type="button"
            onClick={(e) => downloadChatFile(file, e.currentTarget.ownerDocument)}
            style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem" }}
          >
            <Download size={14} aria-hidden />
            Download {file.filename}
          </button>
        </li>
      ))}
    </ul>
  );
}

export interface ChatMessageEditing {
  draft: string;
  onChange: (draft: string) => void;
  onSave: () => void;
  onCancel: () => void;
}

interface Props {
  message: ChatMessage;
  /** Files the assistant exported with this reply. */
  files?: ChatFile[];
  /** True while a reply is pending: editing, regenerating and switching versions are blocked, copying is not. */
  busy: boolean;
  /** Starts editing this message; only passed for the user's own messages. */
  onEdit?: () => void;
  /** Asks for a new reply in place of this one; only passed for assistant replies. */
  onRegenerate?: () => void;
  /** Set while this message is being edited. */
  editing?: ChatMessageEditing;
  /** Set when the message has more than one version. */
  version?: ChatMessageVersion;
}

export function ChatMessageItem({ message, files, busy, onEdit, onRegenerate, editing, version }: Props) {
  const isUser = message.role === "user";
  return (
    <li
      className="chat-message"
      aria-label={isUser ? "You" : "Assistant"}
      style={{
        alignSelf: isUser ? "flex-end" : "stretch",
        maxWidth: isUser ? "85%" : "100%",
        // Widen while editing so the edit box is not squeezed to the old text's width.
        width: editing ? "85%" : undefined,
        background: isUser ? "var(--chat-user-bg)" : "var(--chat-assistant-bg)",
        border: "1px solid var(--drawer-border-color)",
        borderRadius: "0.5rem",
        padding: "0.5rem 0.75rem",
        whiteSpace: isUser ? "pre-wrap" : undefined,
        overflowWrap: "anywhere",
      }}
    >
      {editing ? (
        <EditForm
          draft={editing.draft}
          disabled={busy}
          onChange={editing.onChange}
          onSave={editing.onSave}
          onCancel={editing.onCancel}
        />
      ) : (
        <>
          {isUser ? (
            message.content
          ) : (
            <div className="chat-markdown">
              <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
                {message.content}
              </ReactMarkdown>
            </div>
          )}
          {files && files.length > 0 && <ChatFiles files={files} />}
          <div className="chat-message-footer">
            {version && <VersionSwitcher version={version} busy={busy} />}
            <div className="chat-message-actions">
              <CopyButton text={message.content} />
              {onEdit && (
                <button
                  type="button"
                  className="chat-message-action"
                  aria-label="Edit message"
                  title="Edit"
                  onClick={onEdit}
                  disabled={busy}
                >
                  <Pencil size={14} aria-hidden />
                </button>
              )}
              {onRegenerate && (
                <button
                  type="button"
                  className="chat-message-action"
                  aria-label="Regenerate reply"
                  title="Regenerate"
                  onClick={onRegenerate}
                  disabled={busy}
                >
                  <RefreshCw size={14} aria-hidden />
                </button>
              )}
            </div>
          </div>
        </>
      )}
    </li>
  );
}

export default ChatMessageItem;
