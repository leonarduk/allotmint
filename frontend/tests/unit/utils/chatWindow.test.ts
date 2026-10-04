import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi, Mock } from "vitest";
import * as api from "@/api";
import { emitAuthChange } from "@/authEvents";
import { appendChatMessage, getChatMessages, getChatSyncState, resetChat } from "@/utils/chatConversation";
import { resetChatSyncForTests } from "@/utils/chatSync";
import {
  CHAT_WINDOW_PATH,
  CLOSE_GRACE_MS,
  STALE_MS,
  canDetachChat,
  openChatWindow,
  prefersDetachedChat,
  resetChatWindowForTests,
  useChatWindowHost,
  useDetachedChatWindow,
} from "@/utils/chatWindow";

vi.mock("@/api");
vi.mock("@/demoAuth", () => ({ isDemoSession: vi.fn(() => false) }));

// Records what this window posts; receive() delivers a message from the other window.
class FakeChannel {
  static instances: FakeChannel[] = [];
  posted: Array<Record<string, unknown>> = [];
  closed = false;
  private listeners = new Set<(event: { data: unknown }) => void>();

  constructor(public name: string) {
    FakeChannel.instances.push(this);
  }
  postMessage(message: Record<string, unknown>) {
    this.posted.push(message);
  }
  addEventListener(_type: string, listener: (event: { data: unknown }) => void) {
    this.listeners.add(listener);
  }
  removeEventListener(_type: string, listener: (event: { data: unknown }) => void) {
    this.listeners.delete(listener);
  }
  close() {
    this.closed = true;
  }
  receive(data: unknown) {
    act(() => this.listeners.forEach((l) => l({ data })));
  }
  postedOf(type: string) {
    return this.posted.filter((m) => m.type === type);
  }
}

const channel = () => FakeChannel.instances[0];
const PAGES = [{ path: "/market", label: "Market" }];
const fakePopup = () => ({ closed: false, focus: vi.fn(), close: vi.fn() });

function renderHost(overrides: Partial<Parameters<typeof useChatWindowHost>[0]> = {}) {
  const handlers = {
    pages: PAGES,
    context: { path: "/portfolio/alex" },
    onNavigate: vi.fn(),
    onReattach: vi.fn(),
    ...overrides,
  };
  const hook = renderHook((props: typeof handlers) => useChatWindowHost(props), { initialProps: handlers });
  return { ...hook, handlers };
}

function mainId(): string {
  return channel().posted[0].main as string;
}

beforeEach(() => {
  FakeChannel.instances = [];
  vi.stubGlobal("BroadcastChannel", FakeChannel);
  localStorage.clear();
  sessionStorage.clear();
  resetChatSyncForTests();
  resetChat();
  (api.putChatConversation as Mock).mockResolvedValue({ revision: 1 });
});

afterEach(() => {
  resetChatWindowForTests();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  vi.useRealTimers();
  window.history.replaceState(null, "", "/");
});

describe("main window", () => {
  it("opens the chat window linked to this tab and reports it detached", () => {
    const popup = fakePopup();
    const open = vi.spyOn(window, "open").mockReturnValue(popup as unknown as Window);
    const { result } = renderHost();

    expect(result.current).toBe(false);
    let opened = false;
    act(() => {
      opened = openChatWindow();
    });

    expect(opened).toBe(true);
    expect(result.current).toBe(true);
    const id = mainId();
    expect(open).toHaveBeenCalledWith(
      `${CHAT_WINDOW_PATH}?main=${encodeURIComponent(id)}`,
      `allotmint-chat-${id}`,
      expect.stringContaining("popup")
    );
    expect(popup.focus).toHaveBeenCalled();
    expect(prefersDetachedChat()).toBe(true);
  });

  it("stays attached when the browser blocks the window", () => {
    vi.spyOn(window, "open").mockReturnValue(null);
    const { result } = renderHost();

    expect(openChatWindow()).toBe(false);
    expect(result.current).toBe(false);
    expect(prefersDetachedChat()).toBe(false);
  });

  it("focuses an open chat window instead of opening another", () => {
    const popup = fakePopup();
    const open = vi.spyOn(window, "open").mockReturnValue(popup as unknown as Window);
    renderHost();

    act(() => void openChatWindow());
    act(() => void openChatWindow());

    expect(open).toHaveBeenCalledTimes(1);
    expect(popup.focus).toHaveBeenCalledTimes(2);
  });

  it("opens only offered pages the chat window asks for, and only from its own window", () => {
    vi.spyOn(window, "open").mockReturnValue(fakePopup() as unknown as Window);
    const { handlers } = renderHost();
    act(() => void openChatWindow());

    channel().receive({ type: "navigate", main: mainId(), path: "/market" });
    channel().receive({ type: "navigate", main: mainId(), path: "/admin" });
    channel().receive({ type: "navigate", main: "another-tab", path: "/market" });

    expect(handlers.onNavigate).toHaveBeenCalledTimes(1);
    expect(handlers.onNavigate).toHaveBeenCalledWith("/market");
  });

  it("tells the window the page it opened straight away, before that page loads", () => {
    vi.spyOn(window, "open").mockReturnValue(fakePopup() as unknown as Window);
    renderHost();
    act(() => void openChatWindow());

    channel().receive({ type: "navigate", main: mainId(), path: "/market" });

    expect(channel().postedOf("context").at(-1)?.context).toEqual({ path: "/market" });
  });

  it("reattaches and reopens the drawer when the window's Reattach is pressed", () => {
    vi.spyOn(window, "open").mockReturnValue(fakePopup() as unknown as Window);
    const { result, handlers } = renderHost();
    act(() => void openChatWindow());

    channel().receive({ type: "reattach", main: mainId() });

    expect(result.current).toBe(false);
    expect(handlers.onReattach).toHaveBeenCalled();
    expect(prefersDetachedChat()).toBe(false);
  });

  it("reattaches without opening the drawer when the window is closed", () => {
    vi.useFakeTimers();
    const popup = fakePopup();
    vi.spyOn(window, "open").mockReturnValue(popup as unknown as Window);
    const { result, handlers } = renderHost();
    act(() => void openChatWindow());

    popup.closed = true;
    act(() => vi.advanceTimersByTime(1_000));

    expect(result.current).toBe(false);
    expect(handlers.onReattach).not.toHaveBeenCalled();
  });

  it("finds a window still open after a reload, and reattaches once it goes quiet", () => {
    vi.useFakeTimers();
    const { result } = renderHost();
    expect(channel().postedOf("ping")).toHaveLength(1);

    channel().receive({ type: "hello", main: mainId() });
    expect(result.current).toBe(true);

    act(() => vi.advanceTimersByTime(STALE_MS - 5_000));
    channel().receive({ type: "alive", main: mainId() });
    act(() => vi.advanceTimersByTime(STALE_MS - 5_000));
    expect(result.current).toBe(true);

    act(() => vi.advanceTimersByTime(10_000));
    expect(result.current).toBe(false);
  });

  it("stays detached when the window reloads, but reattaches when it closes", () => {
    vi.useFakeTimers();
    vi.spyOn(window, "open").mockReturnValue(fakePopup() as unknown as Window);
    const { result } = renderHost();
    act(() => void openChatWindow());

    channel().receive({ type: "closing", main: mainId() });
    channel().receive({ type: "hello", main: mainId() });
    act(() => vi.advanceTimersByTime(CLOSE_GRACE_MS + 1_000));
    expect(result.current).toBe(true);

    channel().receive({ type: "closing", main: mainId() });
    act(() => vi.advanceTimersByTime(CLOSE_GRACE_MS + 1_000));
    expect(result.current).toBe(false);
  });

  it("tells the window the page the user is on, when it starts and as it changes", () => {
    vi.spyOn(window, "open").mockReturnValue(fakePopup() as unknown as Window);
    const { rerender, handlers } = renderHost();
    act(() => void openChatWindow());

    channel().receive({ type: "hello", main: mainId() });
    expect(channel().postedOf("context").at(-1)?.context).toEqual({ path: "/portfolio/alex" });

    const research = { path: "/research/VOD.L", ticker: "VOD.L" };
    rerender({ ...handlers, context: research });
    expect(channel().postedOf("context").at(-1)?.context).toEqual(research);
  });

  it("mirrors the conversation both ways, without saving what the window saved", () => {
    vi.spyOn(window, "open").mockReturnValue(fakePopup() as unknown as Window);
    renderHost();
    act(() => void openChatWindow());

    act(() => void appendChatMessage({ role: "user", content: "from main" }));
    const state = channel().postedOf("state").at(-1);
    expect(state?.tree).toMatchObject({ nodes: [{ content: "from main" }] });

    const posted = channel().posted.length;
    const tree = {
      nodes: [{ id: "1", parentId: null, role: "user", content: "from the window" }],
      active: { root: "1" },
      nextId: 2,
    };
    const sync = { owner: "u1", revision: 7, dirty: false, archivePending: false };
    channel().receive({ type: "state", main: mainId(), tree, sync });

    expect(getChatMessages()).toEqual([{ role: "user", content: "from the window" }]);
    expect(getChatSyncState()).toEqual(sync);
    // Adopted, not echoed back, and not saved again from here.
    expect(channel().posted).toHaveLength(posted);
    expect(api.putChatConversation).not.toHaveBeenCalled();
  });

  it("closes the chat window on logout", () => {
    const popup = fakePopup();
    vi.spyOn(window, "open").mockReturnValue(popup as unknown as Window);
    const { result } = renderHost();
    act(() => void openChatWindow());

    act(() => emitAuthChange({ previousToken: "t", nextToken: null }));

    expect(popup.close).toHaveBeenCalled();
    expect(channel().postedOf("logout")).toHaveLength(1);
    expect(result.current).toBe(false);
  });
});

describe("canDetachChat", () => {
  const original = window.matchMedia;
  const matchMedia = (matches: boolean) => {
    window.matchMedia = vi.fn(() => ({ matches }) as MediaQueryList);
  };
  afterEach(() => {
    window.matchMedia = original;
  });

  it("is offered on a wide viewport", () => {
    matchMedia(true);
    expect(canDetachChat()).toBe(true);
  });

  it("is not offered on a narrow viewport", () => {
    matchMedia(false);
    expect(canDetachChat()).toBe(false);
  });

  it("is not offered without BroadcastChannel", () => {
    matchMedia(true);
    vi.stubGlobal("BroadcastChannel", undefined);
    expect(canDetachChat()).toBe(false);
  });
});

describe("detached window", () => {
  const openAsPopup = (main = "tab-1") => window.history.replaceState(null, "", `${CHAT_WINDOW_PATH}?main=${main}`);

  it("says hello to its main window and follows the page the user is on", () => {
    openAsPopup();
    const { result } = renderHook(() => useDetachedChatWindow());

    expect(result.current.linked).toBe(true);
    expect(channel().postedOf("hello")).toEqual([{ type: "hello", main: "tab-1" }]);

    channel().receive({ type: "context", main: "tab-1", context: { path: "/market" } });
    channel().receive({ type: "context", main: "tab-2", context: { path: "/other" } });
    expect(result.current.context).toEqual({ path: "/market" });
  });

  it("asks the main window to navigate, and to reattach before closing", () => {
    openAsPopup();
    const close = vi.spyOn(window, "close").mockImplementation(() => {});
    const { result } = renderHook(() => useDetachedChatWindow());

    act(() => result.current.navigate("/market"));
    act(() => result.current.reattach());

    expect(channel().postedOf("navigate")).toEqual([{ type: "navigate", main: "tab-1", path: "/market" }]);
    expect(channel().postedOf("reattach")).toHaveLength(1);
    expect(close).toHaveBeenCalled();
  });

  it("says hello again when the main window reloads, and closes on logout", () => {
    openAsPopup();
    const close = vi.spyOn(window, "close").mockImplementation(() => {});
    renderHook(() => useDetachedChatWindow());

    channel().receive({ type: "ping", main: "tab-1" });
    expect(channel().postedOf("hello")).toHaveLength(2);

    channel().receive({ type: "logout", main: "tab-1" });
    expect(close).toHaveBeenCalled();
  });

  it("tells the main window when it goes away", () => {
    openAsPopup();
    renderHook(() => useDetachedChatWindow());

    window.dispatchEvent(new Event("pagehide"));

    expect(channel().postedOf("closing")).toHaveLength(1);
  });

  it("is unlinked when not opened from the app", () => {
    const { result } = renderHook(() => useDetachedChatWindow());

    expect(result.current.linked).toBe(false);
    expect(FakeChannel.instances).toHaveLength(0);
  });
});
