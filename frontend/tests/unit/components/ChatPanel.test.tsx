import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi, Mock } from "vitest";
import { ChatPanel } from "@/components/ChatPanel";
import * as api from "@/api";
import { getChatMessages, resetChat, setChatMessages } from "@/utils/chatConversation";
import { resetChatSyncForTests } from "@/utils/chatSync";
import { isDemoSession } from "@/demoAuth";

vi.mock("@/api");
vi.mock("@/demoAuth", () => ({ isDemoSession: vi.fn(() => false) }));

const EMPTY_SAVED = { owner: "u1", revision: 0, conversation: { nodes: [], active: {}, nextId: 1 } };

describe("ChatPanel", () => {
  beforeEach(() => {
    resetChatSyncForTests();
    resetChat();
    (isDemoSession as Mock).mockReturnValue(false);
    (api.getChatConversation as Mock).mockResolvedValue(EMPTY_SAVED);
    (api.putChatConversation as Mock).mockResolvedValue({ revision: 1 });
    (api.archiveChatConversation as Mock).mockResolvedValue({ revision: 1, archived: true });
    (api.deleteChatHistory as Mock).mockResolvedValue(undefined);
  });

  it("renders nothing when closed", () => {
    render(<ChatPanel open={false} onClose={() => {}} />);
    expect(screen.queryByLabelText(/chat message/i)).not.toBeInTheDocument();
  });

  it("sends a message and shows the assistant's reply", async () => {
    (api.postChat as Mock).mockResolvedValueOnce({ reply: "VOD.L is 1.0" });
    const user = userEvent.setup();

    render(<ChatPanel open onClose={() => {}} />);

    await user.type(screen.getByLabelText(/chat message/i), "what's VOD.L trading at?");
    await user.click(screen.getByRole("button", { name: /send/i }));

    expect(screen.getByText(/what's VOD\.L trading at\?/i)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText(/VOD\.L is 1\.0/i)).toBeInTheDocument());
    expect(api.postChat).toHaveBeenCalledWith("what's VOD.L trading at?", [], [], undefined);
  });

  it("sends the available pages and follows the page the assistant opens", async () => {
    const pages = [
      { path: "/transactions", label: "Transactions" },
      { path: "/market", label: "Market" },
    ];
    (api.postChat as Mock).mockResolvedValueOnce({
      reply: "Opening Transactions.",
      navigate_to: "/transactions",
    });
    const onNavigate = vi.fn();
    const user = userEvent.setup();

    render(<ChatPanel open onClose={() => {}} pages={pages} onNavigate={onNavigate} />);

    await user.type(screen.getByLabelText(/chat message/i), "go to the transactions page");
    await user.click(screen.getByRole("button", { name: /send/i }));

    await waitFor(() => expect(onNavigate).toHaveBeenCalledWith("/transactions"));
    expect(api.postChat).toHaveBeenCalledWith("go to the transactions page", [], pages, undefined);
    expect(screen.getByText("Opening Transactions.")).toBeInTheDocument();
  });

  it("ignores a navigate_to that was not one of the offered pages", async () => {
    (api.postChat as Mock).mockResolvedValueOnce({
      reply: "Opening it.",
      navigate_to: "/admin",
    });
    const onNavigate = vi.fn();
    const user = userEvent.setup();

    render(
      <ChatPanel
        open
        onClose={() => {}}
        pages={[{ path: "/market", label: "Market" }]}
        onNavigate={onNavigate}
      />,
    );

    await user.type(screen.getByLabelText(/chat message/i), "go to admin");
    await user.click(screen.getByRole("button", { name: /send/i }));

    await waitFor(() => expect(screen.getByText("Opening it.")).toBeInTheDocument());
    expect(onNavigate).not.toHaveBeenCalled();
  });

  it("sends the page the user is on as context", async () => {
    (api.postChat as Mock).mockResolvedValueOnce({ reply: "ok" });
    const user = userEvent.setup();
    const context = { path: "/research/ARG.TO", ticker: "ARG.TO" };

    render(<ChatPanel open onClose={() => {}} context={context} />);

    await user.type(screen.getByLabelText(/chat message/i), "is this stock a buy");
    await user.click(screen.getByRole("button", { name: /send/i }));

    await waitFor(() => expect(api.postChat).toHaveBeenCalledWith("is this stock a buy", [], [], context));
  });

  it("renders assistant replies as markdown, including GFM tables", async () => {
    (api.postChat as Mock).mockResolvedValueOnce({
      reply: [
        "## Where you're losing money",
        "",
        "**Total drag:** about -£3,043.",
        "",
        "| Ticker | P/L |",
        "|---|---|",
        "| FSFL.L | **-£937** |",
      ].join("\n"),
    });
    const user = userEvent.setup();

    render(<ChatPanel open onClose={() => {}} />);

    await user.type(screen.getByLabelText(/chat message/i), "where am i losing money");
    await user.click(screen.getByRole("button", { name: /send/i }));

    expect(
      await screen.findByRole("heading", { level: 2, name: /where you're losing money/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Ticker" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "FSFL.L" })).toBeInTheDocument();
    expect(screen.getByText("Total drag:").tagName).toBe("STRONG");
    expect(screen.queryByText(/\*\*/)).not.toBeInTheDocument();
  });

  it("does not render raw HTML from assistant replies", async () => {
    (api.postChat as Mock).mockResolvedValueOnce({
      reply: 'hello <img src="x" onerror="alert(1)"> <b>bold</b>',
    });
    const user = userEvent.setup();

    const { container } = render(<ChatPanel open onClose={() => {}} />);

    await user.type(screen.getByLabelText(/chat message/i), "hi");
    await user.click(screen.getByRole("button", { name: /send/i }));

    await screen.findByText(/hello/);
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("b")).toBeNull();
  });

  it("shows an error message when the request fails", async () => {
    (api.postChat as Mock).mockRejectedValueOnce(new Error("network error"));
    const user = userEvent.setup();

    render(<ChatPanel open onClose={() => {}} />);

    await user.type(screen.getByLabelText(/chat message/i), "hi");
    await user.click(screen.getByRole("button", { name: /send/i }));

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/cannot reach server/i));
  });

  it.each([
    [503, /isn't available/i],
    [502, /couldn't reach its AI service/i],
    [429, /too quickly/i],
    [500, /server error/i],
  ])("shows a status-specific message for HTTP %i without echoing backend text", async (status, expected) => {
    const err = Object.assign(new Error("raw backend text"), { status, detail: "raw backend detail" });
    (api.postChat as Mock).mockRejectedValueOnce(err);
    const user = userEvent.setup();

    render(<ChatPanel open onClose={() => {}} />);

    await user.type(screen.getByLabelText(/chat message/i), "hi");
    await user.click(screen.getByRole("button", { name: /send/i }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(expected);
    expect(alert).not.toHaveTextContent(/raw backend|cannot reach server/i);
  });

  it.each([
    ["mcp_unreachable", 502, /tools server \(MCP\).*MCP server is running/i],
    ["llm_unreachable", 502, /AI model.*Ollama/i],
    ["aws_error", 502, /AWS call \(Bedrock or MCP request signing\)/i],
    ["chat_not_configured", 503, /MCP_SERVER_URL is not set/i],
  ])("names the failing piece for error code %s", async (code, status, expected) => {
    const err = Object.assign(new Error("raw backend text"), { status, code, detail: "raw backend detail" });
    (api.postChat as Mock).mockRejectedValueOnce(err);
    const user = userEvent.setup();

    render(<ChatPanel open onClose={() => {}} />);

    await user.type(screen.getByLabelText(/chat message/i), "hi");
    await user.click(screen.getByRole("button", { name: /send/i }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(expected);
    expect(alert).not.toHaveTextContent(/raw backend/i);
  });

  it("falls back to the status message for an unknown error code", async () => {
    const err = Object.assign(new Error("x"), { status: 502, code: "something_new" });
    (api.postChat as Mock).mockRejectedValueOnce(err);
    const user = userEvent.setup();

    render(<ChatPanel open onClose={() => {}} />);

    await user.type(screen.getByLabelText(/chat message/i), "hi");
    await user.click(screen.getByRole("button", { name: /send/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/couldn't reach its AI service/i);
  });

  it("shows a timeout message when the request times out", async () => {
    (api.postChat as Mock).mockRejectedValueOnce(Object.assign(new Error("Request timed out"), { timeout: true }));
    const user = userEvent.setup();

    render(<ChatPanel open onClose={() => {}} />);

    await user.type(screen.getByLabelText(/chat message/i), "hi");
    await user.click(screen.getByRole("button", { name: /send/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/took too long/i);
  });

  it("drops a failed message from history and restores it for retry (#7897)", async () => {
    (api.postChat as Mock)
      .mockRejectedValueOnce(new Error("timed out"))
      .mockResolvedValueOnce({ reply: "Hello!" });
    const user = userEvent.setup();

    render(<ChatPanel open onClose={() => {}} />);

    const input = screen.getByLabelText(/chat message/i);
    await user.type(input, "hi");
    await user.click(screen.getByRole("button", { name: /send/i }));
    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());

    expect(input).toHaveValue("hi");
    await user.click(screen.getByRole("button", { name: /send/i }));

    await waitFor(() => expect(screen.getByText("Hello!")).toBeInTheDocument());
    expect(api.postChat).toHaveBeenLastCalledWith("hi", [], [], undefined);
    expect(screen.getAllByText("hi")).toHaveLength(1);
  });

  it("keeps the conversation when the panel is remounted on another page", async () => {
    (api.postChat as Mock).mockResolvedValueOnce({ reply: "VOD.L is 1.0" });
    const user = userEvent.setup();

    const first = render(<ChatPanel open onClose={() => {}} context={{ path: "/market" }} />);
    await user.type(screen.getByLabelText(/chat message/i), "price of VOD.L?");
    await user.click(screen.getByRole("button", { name: /send/i }));
    await waitFor(() => expect(screen.getByText(/VOD\.L is 1\.0/i)).toBeInTheDocument());
    first.unmount();

    (api.postChat as Mock).mockResolvedValueOnce({ reply: "Up 2%." });
    const context = { path: "/research/VOD.L", ticker: "VOD.L" };
    render(<ChatPanel open onClose={() => {}} context={context} />);

    expect(screen.getByText("price of VOD.L?")).toBeInTheDocument();
    expect(screen.getByText(/VOD\.L is 1\.0/i)).toBeInTheDocument();

    await user.type(screen.getByLabelText(/chat message/i), "and today?");
    await user.click(screen.getByRole("button", { name: /send/i }));
    await waitFor(() => expect(screen.getByText("Up 2%.")).toBeInTheDocument());
    // Prior turns are sent as history, with the page the user is on now.
    expect(api.postChat).toHaveBeenLastCalledWith(
      "and today?",
      [
        { role: "user", content: "price of VOD.L?" },
        { role: "assistant", content: "VOD.L is 1.0" },
      ],
      [],
      context,
    );
  });

  it("starts a fresh conversation only when New chat is clicked", async () => {
    (api.postChat as Mock).mockResolvedValueOnce({ reply: "Hello." });
    const user = userEvent.setup();

    render(<ChatPanel open onClose={() => {}} />);
    expect(screen.getByRole("button", { name: /new chat/i })).toBeDisabled();
    await user.type(screen.getByLabelText(/chat message/i), "hi");
    await user.click(screen.getByRole("button", { name: /send/i }));
    await waitFor(() => expect(screen.getByText("Hello.")).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: /new chat/i }));

    expect(screen.queryByText("Hello.")).not.toBeInTheDocument();
    expect(screen.getByText(/ask about your portfolios/i)).toBeInTheDocument();
  });

  describe("copy and edit (#8590)", () => {
    const conversation = [
      { role: "user" as const, content: "first question" },
      { role: "assistant" as const, content: "**first** answer" },
      { role: "user" as const, content: "second question" },
      { role: "assistant" as const, content: "second answer" },
    ];

    beforeEach(() => {
      vi.clearAllMocks();
      setChatMessages(conversation);
    });

    const items = () => screen.getAllByRole("listitem").filter((li) => li.classList.contains("chat-message"));

    it("copies a user message's text", async () => {
      const user = userEvent.setup();
      render(<ChatPanel open onClose={() => {}} />);

      await user.click(within(items()[0]).getByRole("button", { name: /copy message/i }));

      expect(await navigator.clipboard.readText()).toBe("first question");
      expect(within(items()[0]).getByText("Copied")).toBeInTheDocument();
    });

    it("copies an assistant reply as its Markdown source", async () => {
      const user = userEvent.setup();
      render(<ChatPanel open onClose={() => {}} />);

      await user.click(within(items()[1]).getByRole("button", { name: /copy message/i }));

      expect(await navigator.clipboard.readText()).toBe("**first** answer");
    });

    it("says so when the clipboard is unavailable", async () => {
      const user = userEvent.setup();
      vi.spyOn(navigator.clipboard, "writeText").mockRejectedValueOnce(new Error("denied"));
      render(<ChatPanel open onClose={() => {}} />);

      await user.click(within(items()[0]).getByRole("button", { name: /copy message/i }));

      expect(await within(items()[0]).findByText("Copy failed")).toBeInTheDocument();
    });

    it("offers Edit only on the user's own messages", () => {
      render(<ChatPanel open onClose={() => {}} />);

      expect(within(items()[0]).getByRole("button", { name: /edit message/i })).toBeInTheDocument();
      expect(within(items()[1]).queryByRole("button", { name: /edit message/i })).not.toBeInTheDocument();
    });

    it("regenerates from an edited message, dropping everything after it", async () => {
      (api.postChat as Mock).mockResolvedValueOnce({ reply: "new answer" });
      const user = userEvent.setup();
      render(<ChatPanel open onClose={() => {}} />);

      await user.click(within(items()[0]).getByRole("button", { name: /edit message/i }));
      const box = screen.getByLabelText(/edited message/i);
      expect(box).toHaveValue("first question");
      expect(box).toHaveFocus();
      expect((box as HTMLTextAreaElement).selectionStart).toBe("first question".length);
      await user.clear(box);
      await user.type(box, "better question");
      await user.click(screen.getByRole("button", { name: /save & regenerate/i }));

      await waitFor(() => expect(screen.getByText("new answer")).toBeInTheDocument());
      expect(api.postChat).toHaveBeenCalledWith("better question", [], [], undefined);
      expect(getChatMessages()).toEqual([
        { role: "user", content: "better question" },
        { role: "assistant", content: "new answer" },
      ]);
      expect(screen.queryByText("second question")).not.toBeInTheDocument();
    });

    it("sends only the turns before the edited message as history", async () => {
      (api.postChat as Mock).mockResolvedValueOnce({ reply: "new second answer" });
      const user = userEvent.setup();
      render(<ChatPanel open onClose={() => {}} />);

      await user.click(within(items()[2]).getByRole("button", { name: /edit message/i }));
      const box = screen.getByLabelText(/edited message/i);
      await user.clear(box);
      await user.type(box, "second, rephrased{Enter}");

      await waitFor(() => expect(screen.getByText("new second answer")).toBeInTheDocument());
      expect(api.postChat).toHaveBeenCalledWith("second, rephrased", conversation.slice(0, 2), [], undefined);
      expect(getChatMessages()).toHaveLength(4);
    });

    it("leaves the conversation alone on cancel or an unchanged edit", async () => {
      const user = userEvent.setup();
      render(<ChatPanel open onClose={() => {}} />);

      await user.click(within(items()[0]).getByRole("button", { name: /edit message/i }));
      await user.type(screen.getByLabelText(/edited message/i), " changed{Escape}");
      expect(screen.queryByLabelText(/edited message/i)).not.toBeInTheDocument();

      await user.click(within(items()[0]).getByRole("button", { name: /edit message/i }));
      await user.click(screen.getByRole("button", { name: /save & regenerate/i }));

      expect(api.postChat).not.toHaveBeenCalled();
      expect(getChatMessages()).toEqual(conversation);
    });

    it("restores the pre-edit conversation and keeps the edit for retry on failure", async () => {
      (api.postChat as Mock).mockRejectedValueOnce(Object.assign(new Error("x"), { status: 502 }));
      const user = userEvent.setup();
      render(<ChatPanel open onClose={() => {}} />);

      await user.click(within(items()[0]).getByRole("button", { name: /edit message/i }));
      const box = screen.getByLabelText(/edited message/i);
      await user.clear(box);
      await user.type(box, "better question");
      await user.click(screen.getByRole("button", { name: /save & regenerate/i }));

      expect(await screen.findByRole("alert")).toHaveTextContent(/couldn't reach its AI service/i);
      expect(getChatMessages()).toEqual(conversation);
      expect(screen.getByLabelText(/edited message/i)).toHaveValue("better question");
    });

    it("disables Edit, but not Copy, while a reply is pending", async () => {
      let resolve: (v: { reply: string }) => void = () => {};
      (api.postChat as Mock).mockReturnValueOnce(new Promise((r) => (resolve = r)));
      const user = userEvent.setup();
      render(<ChatPanel open onClose={() => {}} />);

      await user.type(screen.getByLabelText(/chat message/i), "third question");
      await user.click(screen.getByRole("button", { name: /send/i }));

      for (const button of screen.getAllByRole("button", { name: /edit message/i })) {
        expect(button).toBeDisabled();
      }
      for (const button of screen.getAllByRole("button", { name: /copy message/i })) {
        expect(button).toBeEnabled();
      }
      resolve({ reply: "third answer" });
      await waitFor(() => expect(screen.getByText("third answer")).toBeInTheDocument());
    });
  });

  describe("regenerate (#8820)", () => {
    const conversation = [
      { role: "user" as const, content: "first question" },
      { role: "assistant" as const, content: "first answer" },
      { role: "user" as const, content: "second question" },
      { role: "assistant" as const, content: "second answer" },
    ];

    beforeEach(() => {
      vi.clearAllMocks();
      setChatMessages(conversation);
    });

    const items = () =>
      screen.getAllByRole("listitem").filter((li) => li.classList.contains("chat-message"));

    it("offers Regenerate only on assistant replies", () => {
      render(<ChatPanel open onClose={() => {}} />);

      expect(within(items()[0]).queryByRole("button", { name: /regenerate reply/i })).not.toBeInTheDocument();
      expect(within(items()[1]).getByRole("button", { name: /regenerate reply/i })).toBeInTheDocument();
      expect(within(items()[3]).getByRole("button", { name: /regenerate reply/i })).toBeInTheDocument();
    });

    it("regenerates the last reply for the same question", async () => {
      (api.postChat as Mock).mockResolvedValueOnce({ reply: "better second answer" });
      const user = userEvent.setup();
      render(<ChatPanel open onClose={() => {}} />);

      await user.click(within(items()[3]).getByRole("button", { name: /regenerate reply/i }));

      await waitFor(() => expect(screen.getByText("better second answer")).toBeInTheDocument());
      expect(api.postChat).toHaveBeenCalledWith("second question", conversation.slice(0, 2), [], undefined);
      expect(getChatMessages()).toEqual([
        ...conversation.slice(0, 3),
        { role: "assistant", content: "better second answer" },
      ]);
    });

    it("drops every later turn when regenerating an earlier reply", async () => {
      (api.postChat as Mock).mockResolvedValueOnce({ reply: "better first answer" });
      const user = userEvent.setup();
      render(<ChatPanel open onClose={() => {}} />);

      await user.click(within(items()[1]).getByRole("button", { name: /regenerate reply/i }));

      await waitFor(() => expect(screen.getByText("better first answer")).toBeInTheDocument());
      expect(api.postChat).toHaveBeenCalledWith("first question", [], [], undefined);
      expect(getChatMessages()).toEqual([
        { role: "user", content: "first question" },
        { role: "assistant", content: "better first answer" },
      ]);
      expect(screen.queryByText("second question")).not.toBeInTheDocument();
    });

    it("restores the conversation, old reply included, when regenerating fails", async () => {
      (api.postChat as Mock).mockRejectedValueOnce(Object.assign(new Error("x"), { status: 502 }));
      const user = userEvent.setup();
      render(<ChatPanel open onClose={() => {}} />);

      await user.click(within(items()[1]).getByRole("button", { name: /regenerate reply/i }));

      expect(await screen.findByRole("alert")).toHaveTextContent(/couldn't reach its AI service/i);
      expect(getChatMessages()).toEqual(conversation);
      expect(screen.getByText("second answer")).toBeInTheDocument();
    });

    it("disables Regenerate while a reply is pending", async () => {
      let resolve: (v: { reply: string }) => void = () => {};
      (api.postChat as Mock).mockReturnValueOnce(new Promise((r) => (resolve = r)));
      const user = userEvent.setup();
      render(<ChatPanel open onClose={() => {}} />);

      await user.click(within(items()[3]).getByRole("button", { name: /regenerate reply/i }));

      for (const button of screen.getAllByRole("button", { name: /regenerate reply/i })) {
        expect(button).toBeDisabled();
      }
      resolve({ reply: "new answer" });
      await waitFor(() => expect(screen.getByText("new answer")).toBeInTheDocument());
    });

    it("closes an open edit box when a regenerate starts", async () => {
      (api.postChat as Mock).mockResolvedValueOnce({ reply: "new answer" });
      const user = userEvent.setup();
      render(<ChatPanel open onClose={() => {}} />);

      await user.click(within(items()[0]).getByRole("button", { name: /edit message/i }));
      expect(screen.getByLabelText(/edited message/i)).toBeInTheDocument();
      await user.click(within(items()[3]).getByRole("button", { name: /regenerate reply/i }));

      await waitFor(() => expect(screen.getByText("new answer")).toBeInTheDocument());
      expect(screen.queryByLabelText(/edited message/i)).not.toBeInTheDocument();
    });
  });

  describe("versions (#8842)", () => {
    const conversation = [
      { role: "user" as const, content: "first question" },
      { role: "assistant" as const, content: "first answer" },
      { role: "user" as const, content: "second question" },
      { role: "assistant" as const, content: "second answer" },
    ];

    beforeEach(() => {
      vi.clearAllMocks();
      setChatMessages(conversation);
    });

    const items = () =>
      screen.getAllByRole("listitem").filter((li) => li.classList.contains("chat-message"));

    const editFirstQuestion = async (user: ReturnType<typeof userEvent.setup>, text: string) => {
      await user.click(within(items()[0]).getByRole("button", { name: /edit message/i }));
      const box = screen.getByLabelText(/edited message/i);
      await user.clear(box);
      await user.type(box, text);
      await user.click(screen.getByRole("button", { name: /save & regenerate/i }));
    };

    it("shows no version control until a message has another version", () => {
      render(<ChatPanel open onClose={() => {}} />);

      expect(screen.queryByRole("group", { name: /message versions/i })).not.toBeInTheDocument();
    });

    it("keeps the original after an edit and flips back to it with its later turns", async () => {
      (api.postChat as Mock).mockResolvedValueOnce({ reply: "new answer" });
      const user = userEvent.setup();
      render(<ChatPanel open onClose={() => {}} />);

      await editFirstQuestion(user, "better question");
      await waitFor(() => expect(screen.getByText("new answer")).toBeInTheDocument());

      const versions = within(items()[0]).getByRole("group", { name: /message versions/i });
      expect(versions).toHaveTextContent("2 / 2");
      expect(within(versions).getByRole("button", { name: /next version/i })).toBeDisabled();

      await user.click(within(versions).getByRole("button", { name: /previous version/i }));

      expect(getChatMessages()).toEqual(conversation);
      expect(screen.getByText("second answer")).toBeInTheDocument();
      expect(within(items()[0]).getByRole("group", { name: /message versions/i })).toHaveTextContent(
        "1 / 2",
      );
    });

    it("keeps the old reply after a regenerate and flips between them", async () => {
      (api.postChat as Mock).mockResolvedValueOnce({ reply: "better second answer" });
      const user = userEvent.setup();
      render(<ChatPanel open onClose={() => {}} />);

      await user.click(within(items()[3]).getByRole("button", { name: /regenerate reply/i }));
      await waitFor(() => expect(screen.getByText("better second answer")).toBeInTheDocument());
      expect(within(items()[3]).getByRole("group", { name: /message versions/i })).toHaveTextContent(
        "2 / 2",
      );

      await user.click(within(items()[3]).getByRole("button", { name: /previous version/i }));

      expect(screen.getByText("second answer")).toBeInTheDocument();
      expect(screen.queryByText("better second answer")).not.toBeInTheDocument();
    });

    it("continues the selected version and sends only its turns as history", async () => {
      (api.postChat as Mock)
        .mockResolvedValueOnce({ reply: "new answer" })
        .mockResolvedValueOnce({ reply: "third answer" });
      const user = userEvent.setup();
      render(<ChatPanel open onClose={() => {}} />);

      await editFirstQuestion(user, "better question");
      await waitFor(() => expect(screen.getByText("new answer")).toBeInTheDocument());
      await user.click(within(items()[0]).getByRole("button", { name: /previous version/i }));

      await user.type(screen.getByLabelText(/chat message/i), "third question");
      await user.click(screen.getByRole("button", { name: /send/i }));

      await waitFor(() => expect(screen.getByText("third answer")).toBeInTheDocument());
      expect(api.postChat).toHaveBeenLastCalledWith("third question", conversation, [], undefined);
    });

    it("leaves no new version behind when an edit fails", async () => {
      (api.postChat as Mock).mockRejectedValueOnce(Object.assign(new Error("x"), { status: 502 }));
      const user = userEvent.setup();
      render(<ChatPanel open onClose={() => {}} />);

      await editFirstQuestion(user, "better question");

      expect(await screen.findByRole("alert")).toHaveTextContent(/couldn't reach its AI service/i);
      expect(getChatMessages()).toEqual(conversation);
      expect(screen.queryByRole("group", { name: /message versions/i })).not.toBeInTheDocument();
    });

    it("leaves no new version behind when a regenerate fails", async () => {
      (api.postChat as Mock).mockRejectedValueOnce(Object.assign(new Error("x"), { status: 502 }));
      const user = userEvent.setup();
      render(<ChatPanel open onClose={() => {}} />);

      await user.click(within(items()[3]).getByRole("button", { name: /regenerate reply/i }));

      expect(await screen.findByRole("alert")).toBeInTheDocument();
      expect(getChatMessages()).toEqual(conversation);
      expect(screen.queryByRole("group", { name: /message versions/i })).not.toBeInTheDocument();
    });

    it("disables version switching while a reply is pending", async () => {
      (api.postChat as Mock).mockResolvedValueOnce({ reply: "new answer" });
      let resolve: (v: { reply: string }) => void = () => {};
      (api.postChat as Mock).mockReturnValueOnce(new Promise((r) => (resolve = r)));
      const user = userEvent.setup();
      render(<ChatPanel open onClose={() => {}} />);

      await editFirstQuestion(user, "better question");
      await waitFor(() => expect(screen.getByText("new answer")).toBeInTheDocument());
      await user.type(screen.getByLabelText(/chat message/i), "another");
      await user.click(screen.getByRole("button", { name: /send/i }));

      expect(within(items()[0]).getByRole("button", { name: /previous version/i })).toBeDisabled();
      resolve({ reply: "another answer" });
      await waitFor(() => expect(screen.getByText("another answer")).toBeInTheDocument());
      expect(within(items()[0]).getByRole("button", { name: /previous version/i })).toBeEnabled();
    });
  });

  describe("saved conversation (#8870)", () => {
    const savedTree = {
      nodes: [
        { id: "1", parentId: null, role: "user", content: "saved question" },
        { id: "2", parentId: "1", role: "assistant", content: "saved answer" },
      ],
      active: { root: "1", "1": "2" },
      nextId: 3,
    };

    it("shows the saved conversation when opened", async () => {
      (api.getChatConversation as Mock).mockResolvedValue({ owner: "u1", revision: 2, conversation: savedTree });

      render(<ChatPanel open onClose={() => {}} />);

      expect(await screen.findByText("saved answer")).toBeInTheDocument();
      expect(screen.getByText("saved question")).toBeInTheDocument();
    });

    it("New chat archives the saved conversation", async () => {
      (api.getChatConversation as Mock).mockResolvedValue({ owner: "u1", revision: 2, conversation: savedTree });
      const user = userEvent.setup();
      render(<ChatPanel open onClose={() => {}} />);
      await screen.findByText("saved answer");

      await user.click(screen.getByRole("button", { name: /new chat/i }));

      expect(screen.queryByText("saved answer")).not.toBeInTheDocument();
      await waitFor(() => expect(api.archiveChatConversation).toHaveBeenCalledTimes(1));
      expect(api.deleteChatHistory).not.toHaveBeenCalled();
    });

    it("deletes the chat history only after confirming", async () => {
      (api.getChatConversation as Mock).mockResolvedValue({ owner: "u1", revision: 2, conversation: savedTree });
      const user = userEvent.setup();
      render(<ChatPanel open onClose={() => {}} />);
      await screen.findByText("saved answer");

      await user.click(screen.getByRole("button", { name: /delete history/i }));
      const confirm = screen.getByRole("group", { name: /confirm deleting chat history/i });
      await user.click(within(confirm).getByRole("button", { name: /cancel/i }));
      expect(api.deleteChatHistory).not.toHaveBeenCalled();
      expect(screen.getByText("saved answer")).toBeInTheDocument();

      await user.click(screen.getByRole("button", { name: /delete history/i }));
      await user.click(
        within(screen.getByRole("group", { name: /confirm deleting chat history/i })).getByRole("button", {
          name: /^delete$/i,
        }),
      );

      await waitFor(() => expect(screen.queryByText("saved answer")).not.toBeInTheDocument());
      expect(api.deleteChatHistory).toHaveBeenCalledTimes(1);
      expect(screen.queryByRole("group", { name: /confirm deleting/i })).not.toBeInTheDocument();
    });

    it("says so and keeps the conversation when deleting fails", async () => {
      (api.getChatConversation as Mock).mockResolvedValue({ owner: "u1", revision: 2, conversation: savedTree });
      (api.deleteChatHistory as Mock).mockRejectedValue(new Error("down"));
      const user = userEvent.setup();
      render(<ChatPanel open onClose={() => {}} />);
      await screen.findByText("saved answer");

      await user.click(screen.getByRole("button", { name: /delete history/i }));
      await user.click(screen.getByRole("button", { name: /^delete$/i }));

      expect(await screen.findByRole("alert")).toHaveTextContent(/couldn't delete your chat history/i);
      expect(screen.getByText("saved answer")).toBeInTheDocument();
    });

    it("offers no history control in a demo session", () => {
      (isDemoSession as Mock).mockReturnValue(true);
      (api.getChatConversation as Mock).mockClear();
      render(<ChatPanel open onClose={() => {}} />);

      expect(screen.queryByRole("button", { name: /delete history/i })).not.toBeInTheDocument();
      expect(api.getChatConversation).not.toHaveBeenCalled();
    });

    it("shows a Not saved hint when saving fails, and chat keeps working", async () => {
      vi.spyOn(console, "warn").mockImplementation(() => {});
      (api.putChatConversation as Mock).mockRejectedValue(new Error("down"));
      (api.postChat as Mock).mockResolvedValueOnce({ reply: "still answering" });
      const user = userEvent.setup();
      render(<ChatPanel open onClose={() => {}} />);
      await waitFor(() => expect(api.getChatConversation).toHaveBeenCalled());

      await user.type(screen.getByLabelText(/chat message/i), "hello");
      await user.click(screen.getByRole("button", { name: /send/i }));

      expect(await screen.findByText("still answering")).toBeInTheDocument();
      expect(await screen.findByText("Not saved", {}, { timeout: 3000 })).toBeInTheDocument();
    });
  });

  describe("saved chats history", () => {
    const savedTree = {
      nodes: [
        { id: "1", parentId: null, role: "user", content: "current question" },
        { id: "2", parentId: "1", role: "assistant", content: "current answer" },
      ],
      active: { root: "1", "1": "2" },
      nextId: 3,
    };
    const chats = [
      { id: "current", title: "current question", named: false, updated_at: "2026-10-04T09:00:00Z", messages: 2 },
      { id: "r00000001", title: "ISA allowance", named: true, updated_at: "2026-10-01T09:00:00Z", messages: 4 },
    ];

    beforeEach(() => {
      (api.getChatConversation as Mock).mockResolvedValue({ owner: "u1", revision: 2, conversation: savedTree });
      (api.listSavedChats as Mock).mockResolvedValue({ chats });
      (api.renameSavedChat as Mock).mockResolvedValue(undefined);
      (api.deleteSavedChat as Mock).mockResolvedValue(undefined);
      (api.openSavedChat as Mock).mockResolvedValue({
        revision: 4,
        conversation: {
          nodes: [
            { id: "1", parentId: null, role: "user", content: "isa question" },
            { id: "2", parentId: "1", role: "assistant", content: "isa answer" },
          ],
          active: { root: "1", "1": "2" },
          nextId: 3,
        },
        title: "ISA allowance",
      });
    });

    async function openHistory() {
      const user = userEvent.setup();
      render(<ChatPanel open onClose={() => {}} />);
      await screen.findByText("current answer");
      await user.click(screen.getByRole("button", { name: /^history$/i }));
      const list = await screen.findByRole("list", { name: /saved chats/i });
      await within(list).findByText("ISA allowance");
      return { user, list };
    }

    it("lists the saved chats with their names", async () => {
      const { list } = await openHistory();

      expect(within(list).getByText("current question")).toBeInTheDocument();
      expect(within(list).getByText(/current ·/i)).toBeInTheDocument();
      expect(within(list).getByText(/4 messages/)).toBeInTheDocument();
      // The current chat can't be deleted from here; archived ones can.
      expect(within(list).queryByRole("button", { name: /delete current question/i })).not.toBeInTheDocument();
      expect(within(list).getByRole("button", { name: /delete isa allowance/i })).toBeInTheDocument();
    });

    it("opens an archived chat in place of the current one", async () => {
      const { user, list } = await openHistory();

      await user.click(within(list).getByRole("button", { name: "ISA allowance" }));

      expect(await screen.findByText("isa answer")).toBeInTheDocument();
      expect(api.openSavedChat).toHaveBeenCalledWith("r00000001");
      expect(screen.queryByText("current answer")).not.toBeInTheDocument();
      expect(screen.queryByRole("list", { name: /saved chats/i })).not.toBeInTheDocument();
    });

    it("says so and stays on the list when opening fails", async () => {
      vi.spyOn(console, "warn").mockImplementation(() => {});
      (api.openSavedChat as Mock).mockRejectedValue(new Error("down"));
      const { user, list } = await openHistory();

      await user.click(within(list).getByRole("button", { name: "ISA allowance" }));

      expect(await screen.findByRole("alert")).toHaveTextContent(/couldn't open that chat/i);
      await user.click(screen.getByRole("button", { name: /back to chat/i }));
      expect(screen.getByText("current answer")).toBeInTheDocument();
    });

    it("renames a chat", async () => {
      const { user, list } = await openHistory();
      const loads = (api.listSavedChats as Mock).mock.calls.length;

      await user.click(within(list).getByRole("button", { name: /rename isa allowance/i }));
      const input = within(list).getByLabelText(/chat name/i);
      expect(input).toHaveValue("ISA allowance");
      await user.clear(input);
      await user.type(input, "ISA 2026{Enter}");

      await waitFor(() => expect(api.renameSavedChat).toHaveBeenCalledWith("r00000001", "ISA 2026"));
      // The list is reloaded to show the new name.
      await waitFor(() => expect(api.listSavedChats).toHaveBeenCalledTimes(loads + 1));
    });

    it("starts an unnamed chat's rename from an empty box", async () => {
      const { user, list } = await openHistory();

      await user.click(within(list).getByRole("button", { name: /rename current question/i }));

      expect(within(list).getByLabelText(/chat name/i)).toHaveValue("");
    });

    it("deletes one chat only after confirming", async () => {
      const { user, list } = await openHistory();

      await user.click(within(list).getByRole("button", { name: /delete isa allowance/i }));
      const confirm = within(list).getByRole("group", { name: /confirm deleting isa allowance/i });
      await user.click(within(confirm).getByRole("button", { name: /cancel/i }));
      expect(api.deleteSavedChat).not.toHaveBeenCalled();

      await user.click(within(list).getByRole("button", { name: /delete isa allowance/i }));
      await user.click(within(list).getByRole("button", { name: /^delete$/i }));

      await waitFor(() => expect(api.deleteSavedChat).toHaveBeenCalledWith("r00000001"));
    });

    it("says so when the list cannot be loaded", async () => {
      vi.spyOn(console, "warn").mockImplementation(() => {});
      (api.listSavedChats as Mock).mockRejectedValue(new Error("down"));
      const user = userEvent.setup();
      render(<ChatPanel open onClose={() => {}} />);
      await screen.findByText("current answer");

      await user.click(screen.getByRole("button", { name: /^history$/i }));

      expect(await screen.findByRole("alert")).toHaveTextContent(/couldn't load your saved chats/i);
    });

    it("offers no history in a demo session", () => {
      (isDemoSession as Mock).mockReturnValue(true);
      render(<ChatPanel open onClose={() => {}} />);

      expect(screen.queryByRole("button", { name: /^history$/i })).not.toBeInTheDocument();
    });
  });
});
