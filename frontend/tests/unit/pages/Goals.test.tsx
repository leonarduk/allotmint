import { render, screen, waitFor, act, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, beforeEach, vi } from "vitest";
import i18n from "@/i18n";
import Goals from "@/pages/Goals";
import { formatGoalDate, parseGoalForm } from "@/lib/goalForm";

const mockGetGoals = vi.hoisted(() => vi.fn());
const mockCreateGoal = vi.hoisted(() => vi.fn());
const mockGetGoal = vi.hoisted(() => vi.fn());

vi.mock("@/api", async () => {
  const actual = await vi.importActual<typeof import("@/api")>("@/api");
  return {
    ...actual,
    getGoals: mockGetGoals,
    createGoal: mockCreateGoal,
    getGoal: mockGetGoal,
  };
});

beforeEach(() => {
  vi.clearAllMocks();
  mockGetGoals.mockResolvedValue([]);
});

describe("Goals page", () => {
  it("renders translated strings", async () => {
    await act(async () => {
      await i18n.changeLanguage("fr");
    });
    const { unmount } = render(<Goals />, { wrapper: MemoryRouter });
    expect(
      await screen.findByRole("heading", { name: "Objectifs" })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Ajouter un objectif" })
    ).toBeInTheDocument();
    await waitFor(() => expect(mockGetGoals).toHaveBeenCalledTimes(1));
    unmount();
    await act(async () => {
      await i18n.changeLanguage("en");
    });
  });

  it("labels every input", async () => {
    render(<Goals />, { wrapper: MemoryRouter });
    expect(screen.getByLabelText("Name")).toBeInTheDocument();
    expect(screen.getByLabelText("Target Amount")).toHaveValue(null);
    expect(screen.getByLabelText("Target Date")).toBeInTheDocument();
    expect(screen.getByLabelText("Current Amount:")).toHaveAccessibleDescription(
      /used to calculate progress/i
    );
    await waitFor(() => expect(mockGetGoals).toHaveBeenCalled());
  });

  it("shows a validation message on empty submit and keeps the form", async () => {
    render(<Goals />, { wrapper: MemoryRouter });
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "House" } });
    fireEvent.click(screen.getByRole("button", { name: "Add Goal" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/enter a name/i);
    expect(screen.getByLabelText("Name")).toHaveValue("House");
    expect(mockCreateGoal).not.toHaveBeenCalled();
  });

  it("surfaces a save failure", async () => {
    mockCreateGoal.mockRejectedValue(new Error("boom"));
    vi.spyOn(console, "error").mockImplementation(() => {});
    render(<Goals />, { wrapper: MemoryRouter });
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "House" } });
    fireEvent.change(screen.getByLabelText("Target Amount"), { target: { value: "50000" } });
    fireEvent.change(screen.getByLabelText("Target Date"), { target: { value: "2030-01-01" } });
    fireEvent.click(screen.getByRole("button", { name: "Add Goal" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/could not save/i);
    expect(mockCreateGoal).toHaveBeenCalledWith({
      name: "House",
      target_amount: 50000,
      target_date: "2030-01-01",
    });
  });

  it("renders saved goals with formatted currency, localised date and a separate View button", async () => {
    mockGetGoals.mockResolvedValue([
      { name: "House deposit", target_amount: 50000, target_date: "2030-01-01" },
    ]);
    render(<Goals />, { wrapper: MemoryRouter });
    const line = await screen.findByText(/House deposit/);
    expect(line).toHaveTextContent("£50,000.00");
    expect(line).toHaveTextContent(formatGoalDate("2030-01-01", "en"));
    expect(line).not.toHaveTextContent("2030-01-01");
    expect(line).not.toHaveTextContent("View");
    expect(screen.getByRole("button", { name: "View" })).toBeInTheDocument();
  });
});

describe("parseGoalForm", () => {
  it("rejects missing or non-positive values", () => {
    const base = { name: "A", target_amount: "10", target_date: "2030-01-01" };
    expect(parseGoalForm(base)).toEqual({ name: "A", target_amount: 10, target_date: "2030-01-01" });
    expect(parseGoalForm({ ...base, name: "  " })).toBeNull();
    expect(parseGoalForm({ ...base, target_amount: "" })).toBeNull();
    expect(parseGoalForm({ ...base, target_amount: "0" })).toBeNull();
    expect(parseGoalForm({ ...base, target_date: "" })).toBeNull();
  });
});

describe("formatGoalDate", () => {
  it("formats ISO dates without a UTC day shift and passes through junk", () => {
    expect(formatGoalDate("2030-01-01", "en-GB")).toBe("1 Jan 2030");
    expect(formatGoalDate("not-a-date", "en-GB")).toBe("not-a-date");
  });
});
