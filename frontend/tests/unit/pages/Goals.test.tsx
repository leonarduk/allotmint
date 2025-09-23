import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import i18n from "@/i18n";
import Goals from "@/pages/Goals";

const mockGetGoals = vi.hoisted(() => vi.fn());
const mockCreateGoal = vi.hoisted(() => vi.fn());
const mockGetGoal = vi.hoisted(() => vi.fn());

vi.mock("@/api", () => ({
    getGoals: mockGetGoals,
    createGoal: mockCreateGoal,
    getGoal: mockGetGoal,
    getCachedGroupInstruments: undefined,
}));

beforeEach(() => {
  (globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;
  vi.clearAllMocks();
  mockGetGoals.mockResolvedValue([]);
});

describe("Goals page", () => {
  it("renders translated strings", async () => {
    i18n.changeLanguage("fr");
    render(<Goals />, { wrapper: MemoryRouter });
    expect(
      await screen.findByRole("heading", { name: "Objectifs" })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Ajouter un objectif" })
    ).toBeInTheDocument();
    i18n.changeLanguage("en");
  });
});
