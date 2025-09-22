import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import i18n from "../i18n";
import en from "../locales/en/translation.json";
import Trail from "./Trail";

const mockGetTrailTasks = vi.hoisted(() => vi.fn());
const mockCompleteTrailTask = vi.hoisted(() => vi.fn());

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    getTrailTasks: mockGetTrailTasks,
    completeTrailTask: mockCompleteTrailTask,
  };
});

beforeEach(() => {
  (globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;
  vi.clearAllMocks();
});

describe("Trail page", () => {
  it("renders progress header with xp and streak", async () => {
    const today = "2024-01-15";
    mockGetTrailTasks.mockResolvedValue({
      tasks: [
        {
          id: "check_market",
          title: "Check",
          type: "daily",
          commentary: "",
          completed: true,
        },
        {
          id: "review_portfolio",
          title: "Review",
          type: "daily",
          commentary: "",
          completed: false,
        },
      ],
      xp: 10,
      streak: 3,
      daily_totals: { [today]: { completed: 1, total: 2 } },
      today,
    });

    render(<Trail />);

    expect(
      await screen.findByRole("heading", { name: en.trail.title })
    ).toBeInTheDocument();

    const progressText = en.trail.progressLabel
      .replace("{{completed}}", "1")
      .replace("{{total}}", "2")
      .replace("{{percent}}", "50");
    expect(await screen.findByText(progressText)).toBeInTheDocument();

    expect(
      screen.getByText(en.trail.xpLabel.replace("{{xp}}", "10"))
    ).toBeInTheDocument();

    const streakText = i18n.t("trail.streakLabel", { count: 3 });
    expect(screen.getByText(streakText)).toBeInTheDocument();
  });

  it("shows celebration when everything is complete", async () => {
    const today = "2024-01-16";
    mockGetTrailTasks.mockResolvedValue({
      tasks: [
        {
          id: "check_market",
          title: "Check",
          type: "daily",
          commentary: "",
          completed: true,
        },
        {
          id: "review_portfolio",
          title: "Review",
          type: "daily",
          commentary: "",
          completed: true,
        },
        {
          id: "create_goal",
          title: "Goal",
          type: "once",
          commentary: "",
          completed: true,
        },
      ],
      xp: 30,
      streak: 5,
      daily_totals: { [today]: { completed: 2, total: 2 } },
      today,
    });

    render(<Trail />);

    const celebration = await screen.findByRole("status");
    expect(celebration).toHaveAttribute("aria-live", "polite");
    expect(screen.getByText(en.trail.dailyComplete)).toBeInTheDocument();
    expect(screen.getByText(en.trail.allDone)).toBeInTheDocument();
  });
});
