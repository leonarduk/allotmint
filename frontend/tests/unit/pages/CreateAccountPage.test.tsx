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

  it("clears the validation error once the user edits the email field", () => {
    render(
      <MemoryRouter>
        <CreateAccountPage />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole("button", { name: /request account/i }));
    expect(
      screen.getByText(/enter your name and email/i),
    ).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/email/i), {
      target: { value: "a" },
    });

    expect(
      screen.queryByText(/enter your name and email/i),
    ).not.toBeInTheDocument();
  });

  it("clears the validation error once the user edits the note field", () => {
    render(
      <MemoryRouter>
        <CreateAccountPage />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole("button", { name: /request account/i }));
    expect(
      screen.getByText(/enter your name and email/i),
    ).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/what would you like to use allotmint for/i), {
      target: { value: "Tracking my ISA" },
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

  it("logs the HTTP status code when the backend returns 502 for an SES failure (#5375)", async () => {
    // backend.routes.signup returns 502 when send_signup_admin_email raises
    // (SES MessageRejected/Throttling/config errors all collapse to this).
    // api.ts's fetchJson attaches `.status` to the thrown error (see
    // frontend/src/api.ts lines ~253-254), and CreateAccountPage's catch
    // block (lines 141-149) branches on that to log the HTTP status.
    const sesError = new Error("HTTP 502 - Bad Gateway (/signup/request)");
    (sesError as unknown as { status: number }).status = 502;
    vi.mocked(requestAccountSignup).mockRejectedValue(sesError);
    const consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => {});

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

    expect(consoleErrorSpy).toHaveBeenCalledWith(
      "Failed to submit account signup request (HTTP 502)",
      sesError,
    );

    consoleErrorSpy.mockRestore();
  });

  it("logs without an HTTP status when the failure has no status code", async () => {
    const networkError = new Error("network down");
    vi.mocked(requestAccountSignup).mockRejectedValue(networkError);
    const consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => {});

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

    expect(consoleErrorSpy).toHaveBeenCalledWith(
      "Failed to submit account signup request",
      networkError,
    );

    consoleErrorSpy.mockRestore();
  });
});
