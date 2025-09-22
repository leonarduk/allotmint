import { render, screen, cleanup } from "@testing-library/react";
import { describe, it, expect, vi, afterEach } from "vitest";
import type { ReactElement } from "react";
import { I18nextProvider, initReactI18next } from "react-i18next";
import { createInstance } from "i18next";
import en from "../locales/en/translation.json";
import * as api from "../api";

vi.mock("../api");

const mockGetTrailTasks = vi.mocked(api.getTrailTasks);

function renderWithI18n(ui: ReactElement) {
  const i18n = createInstance();
  i18n.use(initReactI18next).init({
    lng: "en",
    resources: { en: { translation: en } },
  });
  return render(<I18nextProvider i18n={i18n}>{ui}</I18nextProvider>);
}

describe("Trail page", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("renders gamified header with celebration when all dailies are complete", async () => {
    const today = new Date().toISOString().slice(0, 10);
    mockGetTrailTasks.mockResolvedValueOnce({
      tasks: [
        {
          id: "check_market",
          title: "Check market overview",
          type: "daily",
          commentary: "",
          completed: true,
        },
        {
          id: "review_portfolio",
          title: "Review your portfolio",
          type: "daily",
          commentary: "",
          completed: true,
        },
        {
          id: "create_goal",
          title: "Set up your first goal",
          type: "once",
          commentary: "",
          completed: false,
        },
        {
          id: "add_watchlist",
          title: "Add a stock to your watchlist",
          type: "once",
          commentary: "",
          completed: false,
        },
      ],
      xp: 20,
      streak: 3,
      daily_totals: { [today]: 2 },
    });
    const { default: Trail } = await import("./Trail");

    renderWithI18n(<Trail />);

    expect(await screen.findByText("Today's progress")).toBeInTheDocument();
    expect(
      screen.getByText("2 of 2 daily tasks complete (100%)"),
    ).toBeInTheDocument();
    expect(screen.getByText("XP")).toBeInTheDocument();
    expect(screen.getByText("20 XP")).toBeInTheDocument();
    expect(screen.getByText("3 day streak")).toBeInTheDocument();
    expect(
      screen.getByText("All daily tasks complete! Fantastic work!"),
    ).toBeInTheDocument();
  });

  it("shows progress without celebration when tasks remain", async () => {
    const today = new Date().toISOString().slice(0, 10);
    mockGetTrailTasks.mockResolvedValueOnce({
      tasks: [
        {
          id: "check_market",
          title: "Check market overview",
          type: "daily",
          commentary: "",
          completed: true,
        },
        {
          id: "review_portfolio",
          title: "Review your portfolio",
          type: "daily",
          commentary: "",
          completed: false,
        },
        {
          id: "create_goal",
          title: "Set up your first goal",
          type: "once",
          commentary: "",
          completed: false,
        },
        {
          id: "add_watchlist",
          title: "Add a stock to your watchlist",
          type: "once",
          commentary: "",
          completed: false,
        },
      ],
      xp: 10,
      streak: 0,
      daily_totals: { [today]: 1 },
    });
    const { default: Trail } = await import("./Trail");

    renderWithI18n(<Trail />);

    expect(await screen.findByText("Today's progress")).toBeInTheDocument();
    expect(
      screen.getByText("1 of 2 daily tasks complete (50%)"),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("All daily tasks complete! Fantastic work!"),
    ).not.toBeInTheDocument();
  });
});
