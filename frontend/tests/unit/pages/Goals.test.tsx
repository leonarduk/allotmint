import { render, screen, waitFor, act } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, beforeEach, vi } from "vitest";
import i18n from "@/i18n";
import Goals from "@/pages/Goals";

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
});
