import { beforeEach, describe, expect, it, vi } from "vitest";

type Store = typeof import("@/utils/chatConversation");

const TREE_KEY = "allotmint.chat.tree.v1";
const LEGACY_KEY = "allotmint.chat.messages";

// The store loads from sessionStorage once, at import: re-import it to
// simulate a reload of the tab.
async function freshStore(): Promise<Store> {
  vi.resetModules();
  return import("@/utils/chatConversation");
}

const contents = (store: Store) => store.getChatMessages().map((m) => m.content);
const versions = (store: Store) =>
  store.getChatPath().map((n) => `${n.version}/${n.versionCount}`);

describe("chatConversation (#8842)", () => {
  let store: Store;

  beforeEach(async () => {
    sessionStorage.clear();
    store = await freshStore();
  });

  it("builds a single branch from appended turns", () => {
    store.appendChatMessage({ role: "user", content: "q1" });
    store.appendChatMessage({ role: "assistant", content: "a1" });

    expect(store.getChatMessages()).toEqual([
      { role: "user", content: "q1" },
      { role: "assistant", content: "a1" },
    ]);
    expect(versions(store)).toEqual(["1/1", "1/1"]);
  });

  it("keeps the old version and its later turns when a version is added", () => {
    store.setChatMessages([
      { role: "user", content: "q1" },
      { role: "assistant", content: "a1" },
      { role: "user", content: "q2" },
      { role: "assistant", content: "a2" },
    ]);
    const q1 = store.getChatPath()[0].id;

    store.addChatVersion(q1, { role: "user", content: "q1 edited" });
    store.appendChatMessage({ role: "assistant", content: "a1 new" });
    expect(contents(store)).toEqual(["q1 edited", "a1 new"]);
    expect(versions(store)).toEqual(["2/2", "1/1"]);

    store.selectChatVersion(store.getChatPath()[0].id, -1);
    expect(contents(store)).toEqual(["q1", "a1", "q2", "a2"]);
    expect(versions(store)).toEqual(["1/2", "1/1", "1/1", "1/1"]);

    store.selectChatVersion(q1, 1);
    expect(contents(store)).toEqual(["q1 edited", "a1 new"]);
  });

  it("makes the next reply a new version after ending the path at a turn", () => {
    store.setChatMessages([
      { role: "user", content: "q1" },
      { role: "assistant", content: "a1" },
    ]);
    const q1 = store.getChatPath()[0].id;

    store.endChatPathAt(q1);
    expect(contents(store)).toEqual(["q1"]);
    store.appendChatMessage({ role: "assistant", content: "a1 again" });

    expect(contents(store)).toEqual(["q1", "a1 again"]);
    expect(versions(store)).toEqual(["1/1", "2/2"]);
  });

  it("ignores a version switch past either end", () => {
    store.setChatMessages([{ role: "user", content: "q1" }]);
    const q1 = store.getChatPath()[0].id;

    store.selectChatVersion(q1, -1);
    store.selectChatVersion(q1, 1);

    expect(contents(store)).toEqual(["q1"]);
  });

  it("restores a snapshot exactly", () => {
    store.setChatMessages([
      { role: "user", content: "q1" },
      { role: "assistant", content: "a1" },
    ]);
    const before = store.snapshotChat();
    store.addChatVersion(store.getChatPath()[0].id, { role: "user", content: "q1 edited" });

    store.restoreChat(before);

    expect(contents(store)).toEqual(["q1", "a1"]);
    expect(versions(store)).toEqual(["1/1", "1/1"]);
  });

  it("keeps versions and the selected branch across a reload", async () => {
    store.setChatMessages([
      { role: "user", content: "q1" },
      { role: "assistant", content: "a1" },
    ]);
    store.addChatVersion(store.getChatPath()[0].id, { role: "user", content: "q1 edited" });
    store.appendChatMessage({ role: "assistant", content: "a1 new" });

    const reloaded = await freshStore();

    expect(contents(reloaded)).toEqual(["q1 edited", "a1 new"]);
    expect(versions(reloaded)).toEqual(["2/2", "1/1"]);
    reloaded.appendChatMessage({ role: "user", content: "q2" });
    expect(new Set(reloaded.getChatPath().map((n) => n.id)).size).toBe(3);
  });

  it("migrates a conversation stored in the old flat format", async () => {
    sessionStorage.setItem(
      LEGACY_KEY,
      JSON.stringify([
        { role: "user", content: "q1" },
        { role: "assistant", content: "a1" },
        { role: "system", content: "dropped" },
      ]),
    );

    const migrated = await freshStore();
    expect(contents(migrated)).toEqual(["q1", "a1"]);

    migrated.appendChatMessage({ role: "user", content: "q2" });
    expect(sessionStorage.getItem(LEGACY_KEY)).toBeNull();
    expect(sessionStorage.getItem(TREE_KEY)).not.toBeNull();
  });

  it("drops malformed stored nodes and starts empty on unreadable data", async () => {
    sessionStorage.setItem(
      TREE_KEY,
      JSON.stringify({
        nodes: [
          { id: "1", parentId: null, role: "user", content: "q1" },
          { id: "2", parentId: "missing", role: "assistant", content: "orphan" },
          { id: "3", parentId: "1", role: "bogus", content: "bad role" },
        ],
        active: { root: "1", "1": "2" },
        nextId: 4,
      }),
    );
    expect(contents(await freshStore())).toEqual(["q1"]);

    sessionStorage.setItem(TREE_KEY, "{not json");
    expect(contents(await freshStore())).toEqual([]);
  });

  it("clears every version on a new chat", () => {
    store.setChatMessages([{ role: "user", content: "q1" }]);
    store.addChatVersion(store.getChatPath()[0].id, { role: "user", content: "q1 edited" });

    store.startNewChat();

    expect(store.getChatPath()).toEqual([]);
  });
});

// Exercises the auth-change subscriber directly, independent of
// api.setAuthToken (whose end-to-end behaviour is covered in api.test.ts).
describe("chat conversation auth-change subscriber", () => {
  let store: Store;
  let emitAuthChange: typeof import("@/authEvents").emitAuthChange;

  beforeEach(async () => {
    sessionStorage.clear();
    store = await freshStore();
    // Same module graph as the fresh store, so this reaches its subscriber.
    ({ emitAuthChange } = await import("@/authEvents"));
    store.appendChatMessage({ role: "user", content: "What is my ISA worth?" });
  });

  it("clears the conversation on a logout event", async () => {
    emitAuthChange({ previousToken: "token-for-user-a", nextToken: null });

    expect(store.getChatPath()).toEqual([]);
    expect(contents(await freshStore())).toEqual([]);
  });

  it("keeps the conversation when a token is applied from null", () => {
    emitAuthChange({ previousToken: null, nextToken: "token-for-user-a" });

    expect(contents(store)).toEqual(["What is my ISA worth?"]);
  });

  it("keeps the conversation on a token refresh", () => {
    emitAuthChange({
      previousToken: "token-for-user-a",
      nextToken: "refreshed-token-for-user-a",
    });

    expect(contents(store)).toEqual(["What is my ISA worth?"]);
  });
});
