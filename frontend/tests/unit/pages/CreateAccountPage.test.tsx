import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import CreateAccountPage from "@/pages/CreateAccountPage";
import { requestAccountSignup } from "@/api";

vi.mock("@/api", () => ({
  requestAccountSignup: vi.fn(),
}));

describe("CreateAccountPage", () => {
  beforeEach(() => {
    vi.mocked(requestAccountSignup).mockReset();
  });

  it("blocks submission with empty fields and shows a validation message", () => {
    render(
      <MemoryRouter>
        <CreateAccountPage />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole("button", { name: /request account/i }));

    expect(
      screen.getByText(/enter your name and email/i),
    ).toBeInTheDocument();
    expect(requestAccountSignup).not.toHaveBeenCalled();
  });

  it("blocks submission with an invalid email", () => {
    render(
      <MemoryRouter>
        <CreateAccountPage />
      </MemoryRouter>,
    );

    fireEvent.change(screen.getByLabelText(/full name/i), {
      target: { value: "Ada Lovelace" },
    });
    fireEvent.change(screen.getByLabelText(/email/i), {
      target: { value: "not-an-email" },
    });
    fireEvent.click(screen.getByRole("button", { name: /request account/i }));

    expect(screen.getByText(/valid email address/i)).toBeInTheDocument();
    expect(requestAccountSignup).not.toHaveBeenCalled();
  });

  it("submits valid details and shows a pending-approval confirmation", async () => {
    vi.mocked(requestAccountSignup).mockResolvedValue({ status: "pending" });

    render(
      <MemoryRouter>
        <CreateAccountPage />
      </MemoryRouter>,
    );

    fireEvent.change(screen.getByLabelText(/full name/i), {
      target: { value: "Ada Lovelace" },
    });
    fireEvent.change(screen.getByLabelText(/email/i), {
      target: { value: "ada@example.com" },
    });
    fireEvent.click(screen.getByRole("button", { name: /request account/i }));

    await waitFor(() =>
      expect(requestAccountSignup).toHaveBeenCalledWith({
        name: "Ada Lovelace",
        email: "ada@example.com",
        note: undefined,
      }),
    );

    expect(
      await screen.findByText(/pending admin approval/i),
    ).toBeInTheDocument();
  });

  it("clears the validation error once the user edits a field", () => {
    render(
      <MemoryRouter>
        <CreateAccountPage />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole("button", { name: /request account/i }));
    expect(
      screen.getByText(/enter your name and email/i),
    ).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/full name/i), {
      target: { value: "A" },
    });

    expect(
      screen.queryByText(/enter your name and email/i),
    ).not.toBeInTheDocument();
  });

  it("shows an error message and stays on the form when submission fails", async () => {
    vi.mocked(requestAccountSignup).mockRejectedValue(new Error("network"));

    render(
      <MemoryRouter>
        <CreateAccountPage />
      </MemoryRouter>,
    );

    fireEvent.change(screen.getByLabelText(/full name/i), {
      target: { value: "Ada Lovelace" },
    });
    fireEvent.change(screen.getByLabelText(/email/i), {
      target: { value: "ada@example.com" },
    });
    fireEvent.click(screen.getByRole("button", { name: /request account/i }));

    expect(
      await screen.findByText(/something went wrong/i),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /request account/i }),
    ).toBeInTheDocument();
  });
});
