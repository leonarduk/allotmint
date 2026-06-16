import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { AddAccountForm } from "@/components/AddAccountForm";
import { createAccount } from "@/api";

vi.mock("@/api", () => ({
  createAccount: vi.fn(),
}));

describe("AddAccountForm", () => {
  beforeEach(() => {
    vi.mocked(createAccount).mockReset();
  });

  it("submits the selected account type and currency", async () => {
    vi.mocked(createAccount).mockResolvedValue({
      status: "created",
      owner: "alice",
      account: "isa",
      currency: "GBP",
    });
    const onCreated = vi.fn();

    render(<AddAccountForm owner="alice" onCreated={onCreated} />);

    fireEvent.change(screen.getByLabelText(/account type/i), {
      target: { value: "sipp" },
    });
    fireEvent.click(screen.getByRole("button", { name: /add account/i }));

    await waitFor(() =>
      expect(createAccount).toHaveBeenCalledWith({
        owner: "alice",
        account_type: "sipp",
        currency: "GBP",
      }),
    );
    expect(onCreated).toHaveBeenCalledWith("isa");
  });

  it("supports a custom account type", async () => {
    vi.mocked(createAccount).mockResolvedValue({
      status: "created",
      owner: "alice",
      account: "junior-isa",
      currency: "GBP",
    });

    render(<AddAccountForm owner="alice" onCreated={vi.fn()} />);

    fireEvent.change(screen.getByLabelText(/account type/i), {
      target: { value: "other" },
    });
    fireEvent.change(screen.getByLabelText(/custom account type/i), {
      target: { value: "Junior-ISA" },
    });
    fireEvent.click(screen.getByRole("button", { name: /add account/i }));

    await waitFor(() =>
      expect(createAccount).toHaveBeenCalledWith({
        owner: "alice",
        account_type: "junior-isa",
        currency: "GBP",
      }),
    );
  });

  it("shows a friendly message when the account already exists (409)", async () => {
    const err = new Error("HTTP 409 - Conflict") as Error & { status: number };
    err.status = 409;
    vi.mocked(createAccount).mockRejectedValue(err);

    render(<AddAccountForm owner="alice" onCreated={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: /add account/i }));

    expect(await screen.findByText(/already exists/i)).toBeInTheDocument();
  });

  it("shows a generic error message on unexpected failures", async () => {
    vi.mocked(createAccount).mockRejectedValue(new Error("network"));

    render(<AddAccountForm owner="alice" onCreated={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: /add account/i }));

    expect(await screen.findByText(/something went wrong/i)).toBeInTheDocument();
  });

  it("requires a custom account type when 'Other' is selected", () => {
    render(<AddAccountForm owner="alice" onCreated={vi.fn()} />);

    fireEvent.change(screen.getByLabelText(/account type/i), {
      target: { value: "other" },
    });
    fireEvent.click(screen.getByRole("button", { name: /add account/i }));

    expect(screen.getByText(/choose or enter an account type/i)).toBeInTheDocument();
    expect(createAccount).not.toHaveBeenCalled();
  });

  it("calls onCancel when the cancel button is clicked", () => {
    const onCancel = vi.fn();
    render(<AddAccountForm owner="alice" onCreated={vi.fn()} onCancel={onCancel} />);

    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));

    expect(onCancel).toHaveBeenCalled();
  });
});
