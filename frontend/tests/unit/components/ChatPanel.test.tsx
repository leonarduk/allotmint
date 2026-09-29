import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, Mock } from "vitest";
import { ChatPanel } from "@/components/ChatPanel";
import * as api from "@/api";

vi.mock("@/api");

describe("ChatPanel", () => {
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
    expect(api.postChat).toHaveBeenCalledWith("what's VOD.L trading at?", [], []);
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
    expect(api.postChat).toHaveBeenCalledWith("go to the transactions page", [], pages);
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
    expect(api.postChat).toHaveBeenLastCalledWith("hi", [], []);
    expect(screen.getAllByText("hi")).toHaveLength(1);
  });
});
