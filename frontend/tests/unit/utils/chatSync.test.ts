import { afterEach, beforeEach, describe, expect, it, vi, Mock } from "vitest";
import * as api from "@/api";
import { isDemoSession } from "@/demoAuth";
import { emitAuthChange } from "@/authEvents";
import {
  appendChatMessage,
  getChatMessages,
  getChatSyncState,
  markChatIdentityChanged,
  resetChat,
  setChatSyncState,
} from "@/utils/chatConversation";
import {
  SAVE_DEBOUNCE_MS,
  deleteSavedChatHistory,
  ensureChatLoaded,
  flush,
  resetChatSyncForTests,
  setChatReplyPending,
  startNewSavedChat,
} from "@/utils/chatSync";

vi.mock("@/api");
vi.mock("@/demoAuth", () => ({ isDemoSession: vi.fn(() => false) }));

const EMPTY = { nodes: [], active: {}, nextId: 1 };
const tree = (...contents: string[]) => {
  const nodes = contents.map((content, i) => ({
    id: String(i + 1),
    parentId: i === 0 ? null : String(i),
    role: i % 2 === 0 ? ("user" as const) : ("assistant" as const),
    content,
  }));
  const active: Record<string, string> = {};
  nodes.forEach((n) => (active[n.parentId ?? "root"] = n.id));
  return { nodes, active, nextId: nodes.length + 1 };
};
const saved = (owner: string, revision: number, conversation = EMPTY) => ({ owner, revision, conversation });
const contents = () => getChatMessages().map((m) => m.content);
const user = (content: string) => ({ role: "user" as const, content });
const assistant = (content: string) => ({ role: "assistant" as const, content });

const getMock = () => api.getChatConversation as Mock;
const putMock = () => api.putChatConversation as Mock;

async function settle() {
  await vi.advanceTimersByTimeAsync(SAVE_DEBOUNCE_MS + 10);
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.spyOn(console, "warn").mockImplementation(() => {});
  resetChatSyncForTests();
  resetChat();
  (isDemoSession as Mock).mockReturnValue(false);
  getMock().mockReset().mockResolvedValue(saved("alice", 0));
  putMock().mockReset().mockImplementation((_tree, revision: number) => Promise.resolve({ revision: revision + 1 }));
  (api.archiveChatConversation as Mock).mockReset().mockResolvedValue({ revision: 1, archived: true });
  (api.deleteChatHistory as Mock).mockReset().mockResolvedValue(undefined);
});

afterEach(() => {
  resetChatSyncForTests();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("loading", () => {
  it("adopts the saved conversation", async () => {
    getMock().mockResolvedValue(saved("alice", 4, tree("q", "a")));

    await ensureChatLoaded();

    expect(contents()).toEqual(["q", "a"]);
    expect(getChatSyncState()).toEqual({ owner: "alice", revision: 4, dirty: false, archivePending: false });
    expect(putMock()).not.toHaveBeenCalled();
  });

  it("loads once per identity", async () => {
    await ensureChatLoaded();
    await ensureChatLoaded();
    expect(getMock()).toHaveBeenCalledTimes(1);

    markChatIdentityChanged();
    await ensureChatLoaded();
    expect(getMock()).toHaveBeenCalledTimes(2);
  });

  it("uploads a local conversation when nothing is saved yet", async () => {
    appendChatMessage(user("from before sync"));

    await ensureChatLoaded();

    expect(putMock()).toHaveBeenCalledWith(expect.objectContaining({ nodes: expect.any(Array) }), 0);
    expect(contents()).toEqual(["from before sync"]);
    expect(getChatSyncState()).toMatchObject({ owner: "alice", revision: 1, dirty: false });
  });

  it("keeps an unsynced local conversation and archives the different saved one", async () => {
    appendChatMessage(user("local"));
    getMock().mockResolvedValue(saved("alice", 2, tree("saved")));
    (api.archiveChatConversation as Mock).mockResolvedValue({ revision: 3, archived: true });

    await ensureChatLoaded();

    // Neither copy is lost: the saved one goes to the archive, then the local one is saved.
    expect(contents()).toEqual(["local"]);
    expect(api.archiveChatConversation).toHaveBeenCalledTimes(1);
    expect(putMock()).toHaveBeenCalledWith(expect.anything(), 3);
    expect(getChatSyncState()).toMatchObject({ owner: "alice", revision: 4, dirty: false, archivePending: false });
  });

  it("saves unsaved changes for the same user instead of losing them", async () => {
    setChatSyncState({ owner: "alice", revision: 2, dirty: false, archivePending: false });
    appendChatMessage(user("unsaved"));
    getMock().mockResolvedValue(saved("alice", 2, tree("older")));

    await ensureChatLoaded();

    expect(putMock()).toHaveBeenCalledWith(expect.anything(), 2);
    expect(contents()).toEqual(["unsaved"]);
  });

  it.each([
    ["has a saved chat", tree("bob's chat"), ["bob's chat"]],
    // The dangerous case: an empty account would otherwise take the upload.
    ["has nothing saved", EMPTY, []],
  ])("never uploads a conversation cached for a different user who %s", async (_, bobs, expected) => {
    setChatSyncState({ owner: "alice", revision: 2, dirty: false, archivePending: true });
    appendChatMessage(user("alice's holdings"));
    markChatIdentityChanged();
    getMock().mockResolvedValue(saved("bob", 1, bobs));

    await ensureChatLoaded();
    await settle();

    expect(contents()).toEqual(expected);
    expect(putMock()).not.toHaveBeenCalled();
    expect(api.archiveChatConversation).not.toHaveBeenCalled();
    expect(getChatSyncState()).toEqual({ owner: "bob", revision: 1, dirty: false, archivePending: false });
  });

  it("keeps the local conversation when loading fails", async () => {
    appendChatMessage(user("local"));
    getMock().mockRejectedValue(new Error("offline"));

    await ensureChatLoaded();

    expect(contents()).toEqual(["local"]);
    expect(putMock()).not.toHaveBeenCalled();
    expect(console.warn).toHaveBeenCalled();
  });

  it("does not drop a question sent while the first load was in flight", async () => {
    let answer: (value: unknown) => void = () => {};
    getMock().mockReturnValueOnce(new Promise((resolve) => (answer = resolve)));
    const loading = ensureChatLoaded();

    setChatReplyPending(true);
    appendChatMessage(user("quick question"));
    answer(saved("alice", 2, tree("older chat")));
    await loading;
    expect(contents()).toEqual(["quick question"]);

    appendChatMessage(assistant("reply"));
    getMock().mockResolvedValue(saved("alice", 2, tree("older chat")));
    setChatReplyPending(false);
    await settle();

    // Loaded again once the reply was in. The new exchange is kept and the
    // older saved chat archived, so neither is lost.
    expect(getMock()).toHaveBeenCalledTimes(2);
    expect(contents()).toEqual(["quick question", "reply"]);
    expect(api.archiveChatConversation).toHaveBeenCalledTimes(1);
    expect(putMock()).toHaveBeenCalledTimes(1);
  });

  it("treats an unexpected response as a failed load", async () => {
    getMock().mockResolvedValue(undefined);
    appendChatMessage(user("local"));

    await ensureChatLoaded();

    expect(contents()).toEqual(["local"]);
    expect(putMock()).not.toHaveBeenCalled();
  });
});

describe("saving", () => {
  beforeEach(async () => {
    await ensureChatLoaded();
  });

  it("debounces changes into one save", async () => {
    appendChatMessage(user("q"));
    appendChatMessage(assistant("a"));
    expect(putMock()).not.toHaveBeenCalled();

    await settle();

    expect(putMock()).toHaveBeenCalledTimes(1);
    expect(putMock().mock.calls[0][0].nodes).toHaveLength(2);
    expect(getChatSyncState()).toMatchObject({ revision: 1, dirty: false });
  });

  it("holds saves while a reply is pending", async () => {
    setChatReplyPending(true);
    appendChatMessage(user("q"));
    await settle();
    expect(putMock()).not.toHaveBeenCalled();

    appendChatMessage(assistant("a"));
    setChatReplyPending(false);
    await settle();

    expect(putMock()).toHaveBeenCalledTimes(1);
    expect(putMock().mock.calls[0][0].nodes).toHaveLength(2);
  });

  it("adopts the saved copy on a conflict", async () => {
    putMock().mockRejectedValue({
      status: 409,
      body: { current: { revision: 6, conversation: tree("other device") } },
    });
    appendChatMessage(user("mine"));

    await settle();

    expect(contents()).toEqual(["other device"]);
    expect(getChatSyncState()).toMatchObject({ revision: 6, dirty: false });
  });

  it("keeps working locally on failure and retries on the next change", async () => {
    putMock().mockRejectedValueOnce(new Error("down"));
    appendChatMessage(user("q"));
    await settle();

    expect(contents()).toEqual(["q"]);
    expect(getChatSyncState().dirty).toBe(true);
    expect(console.warn).toHaveBeenCalled();

    appendChatMessage(assistant("a"));
    await settle();

    expect(putMock()).toHaveBeenCalledTimes(2);
    expect(getChatSyncState().dirty).toBe(false);
  });

  it("ignores a save that finishes after logout", async () => {
    let finish: (value: unknown) => void = () => {};
    putMock().mockImplementation(() => new Promise((_resolve, reject) => (finish = reject)));
    appendChatMessage(user("alice's"));
    await settle();

    resetChat();
    finish({ status: 409, body: { current: { revision: 3, conversation: tree("alice's saved") } } });
    await settle();

    expect(contents()).toEqual([]);
    expect(getChatSyncState()).toEqual({ owner: null, revision: 0, dirty: false, archivePending: false });
  });
});

describe("new chat and deleting history", () => {
  beforeEach(async () => {
    getMock().mockResolvedValue(saved("alice", 3, tree("q", "a")));
    await ensureChatLoaded();
  });

  it("New chat clears the conversation and archives the saved one", async () => {
    startNewSavedChat();
    await settle();

    expect(contents()).toEqual([]);
    expect(api.archiveChatConversation).toHaveBeenCalledTimes(1);
    expect(putMock()).not.toHaveBeenCalled();
    expect(getChatSyncState()).toMatchObject({ revision: 1, archivePending: false, dirty: false });
  });

  it("retries a failed archive before the next save", async () => {
    (api.archiveChatConversation as Mock).mockRejectedValueOnce(new Error("down"));
    startNewSavedChat();
    await settle();
    expect(getChatSyncState().archivePending).toBe(true);

    appendChatMessage(user("new topic"));
    await settle();

    expect(api.archiveChatConversation).toHaveBeenCalledTimes(2);
    expect(putMock()).toHaveBeenCalledWith(expect.anything(), 1);
    expect(getChatSyncState()).toMatchObject({ archivePending: false, dirty: false });
  });

  it("a pending archive survives a reload instead of the old chat coming back", async () => {
    (api.archiveChatConversation as Mock).mockRejectedValueOnce(new Error("down"));
    startNewSavedChat();
    await settle();

    resetChatSyncForTests(); // as after a reload: nothing loaded yet
    await ensureChatLoaded();

    expect(contents()).toEqual([]);
    expect(api.archiveChatConversation).toHaveBeenCalledTimes(2);
  });

  it("deletes the saved history and clears the conversation", async () => {
    await deleteSavedChatHistory();

    expect(api.deleteChatHistory).toHaveBeenCalledTimes(1);
    expect(contents()).toEqual([]);
    expect(getChatSyncState()).toMatchObject({ revision: 0, dirty: false, archivePending: false });
  });

  it("keeps the conversation when deleting fails", async () => {
    (api.deleteChatHistory as Mock).mockRejectedValue(new Error("down"));

    await expect(deleteSavedChatHistory()).rejects.toThrow("down");

    expect(contents()).toEqual(["q", "a"]);
  });

  it("drops a debounced save instead of recreating the history after deleting", async () => {
    appendChatMessage(user("more"));

    await deleteSavedChatHistory();
    await settle();

    expect(putMock()).not.toHaveBeenCalled();
    expect(api.deleteChatHistory).toHaveBeenCalledTimes(1);
  });

  it("waits for a save already in flight before deleting", async () => {
    const order: string[] = [];
    let finishPut: () => void = () => {};
    putMock().mockImplementation(
      () =>
        new Promise((resolve) => {
          finishPut = () => {
            order.push("put done");
            resolve({ revision: 4 });
          };
        }),
    );
    (api.deleteChatHistory as Mock).mockImplementation(async () => {
      order.push("delete");
    });
    appendChatMessage(user("more"));
    await settle(); // the save is now running

    const deleting = deleteSavedChatHistory();
    await vi.advanceTimersByTimeAsync(0);
    expect(order).toEqual([]);
    finishPut();
    await deleting;

    expect(order).toEqual(["put done", "delete"]);
    expect(contents()).toEqual([]);
  });
});

describe("auth changes", () => {
  it("logging out clears the tab without saving an empty chat over the saved one", async () => {
    getMock().mockResolvedValue(saved("alice", 3, tree("q", "a")));
    await ensureChatLoaded();

    emitAuthChange({ previousToken: "alice-token", nextToken: null });
    await settle();

    expect(contents()).toEqual([]);
    expect(putMock()).not.toHaveBeenCalled();
    expect(api.archiveChatConversation).not.toHaveBeenCalled();
    expect(getChatSyncState().owner).toBeNull();
  });

  it("a new token makes the next save reload first", async () => {
    await ensureChatLoaded();
    emitAuthChange({ previousToken: "alice-token", nextToken: "other-token" });

    appendChatMessage(user("q"));
    await settle();

    expect(getMock()).toHaveBeenCalledTimes(2);
  });
});

describe("demo sessions", () => {
  it("never load or save", async () => {
    (isDemoSession as Mock).mockReturnValue(true);

    await ensureChatLoaded();
    appendChatMessage(user("q"));
    startNewSavedChat();
    await flush();
    await settle();

    expect(getMock()).not.toHaveBeenCalled();
    expect(putMock()).not.toHaveBeenCalled();
    expect(api.archiveChatConversation).not.toHaveBeenCalled();
  });
});
