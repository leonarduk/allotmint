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

  it("shows an error message when the request fails", async () => {
    (api.postChat as Mock).mockRejectedValueOnce(new Error("network error"));
    const user = userEvent.setup();

    render(<ChatPanel open onClose={() => {}} />);

    await user.type(screen.getByLabelText(/chat message/i), "hi");
    await user.click(screen.getByRole("button", { name: /send/i }));

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/cannot reach server/i));
  });
});
