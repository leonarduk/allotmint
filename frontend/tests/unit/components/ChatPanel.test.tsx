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
    expect(api.postChat).toHaveBeenCalledWith("what's VOD.L trading at?", []);
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
    expect(api.postChat).toHaveBeenLastCalledWith("hi", []);
    expect(screen.getAllByText("hi")).toHaveLength(1);
  });
});
