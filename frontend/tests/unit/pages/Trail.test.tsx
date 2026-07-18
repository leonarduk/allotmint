import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import i18n from "@/i18n";
import en from "@/locales/en/translation.json";
import Trail from "@/pages/Trail";

const mockGetTrailTasks = vi.hoisted(() => vi.fn());
const mockCompleteTrailTask = vi.hoisted(() => vi.fn());

vi.mock("@/api", async () => {
  const actual = await vi.importActual<typeof import("@/api")>("@/api");
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
    const progressBar = await screen.findByRole("progressbar");
    expect(progressBar).toHaveAttribute("aria-valuetext", progressText);
    expect(progressBar).toHaveAttribute("aria-valuenow", "1");
    expect(progressBar).toHaveAttribute("aria-valuemax", "2");
    expect(await screen.findByText(progressText)).toBeInTheDocument();

    expect(
      screen.getByText(en.trail.xpLabel.replace("{{xp}}", "10"))
    ).toBeInTheDocument();

    const streakText = i18n.t("trail.streakLabel", { count: 3 });
    expect(screen.getByLabelText(streakText)).toBeInTheDocument();
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

    expect(await screen.findByText(en.trail.dailyComplete)).toBeInTheDocument();
    expect(screen.getByText(en.trail.allDone)).toBeInTheDocument();
  });

  it("shows a loading state before data arrives", () => {
    mockGetTrailTasks.mockReturnValue(new Promise(() => undefined));

    render(<Trail />);

    expect(screen.getByText(en.common.loading)).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: en.trail.title })).not.toBeInTheDocument();
  });

  it("shows an error state when loading trail data fails", async () => {
    mockGetTrailTasks.mockRejectedValue(new Error("network down"));

    render(<Trail />);

    expect(await screen.findByText("Error: network down")).toBeInTheDocument();
    expect(screen.queryByText(en.common.loading)).not.toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: en.trail.title })
    ).not.toBeInTheDocument();
  });

  it("renders an empty task list without daily or completion sections", async () => {
    const today = "2024-01-17";
    mockGetTrailTasks.mockResolvedValue({
      tasks: [],
      xp: 0,
      streak: 0,
      daily_totals: {},
      today,
    });

    render(<Trail />);

    expect(
      await screen.findByRole("heading", { name: en.trail.title })
    ).toBeInTheDocument();

    const progressText = en.trail.progressLabel
      .replace("{{completed}}", "0")
      .replace("{{total}}", "0")
      .replace("{{percent}}", "0");
    expect(screen.getByText(progressText)).toBeInTheDocument();
    expect(screen.queryByText("Check")).not.toBeInTheDocument();
    // An empty task list is vacuously "all complete", so the completion
    // banner shows, but the daily-specific message must not (0 of 0 daily
    // tasks isn't a meaningful "daily complete").
    expect(screen.queryByText(en.trail.dailyComplete)).not.toBeInTheDocument();
    expect(screen.getByText(en.trail.allDone)).toBeInTheDocument();
  });

  it("shows partial-completion state without the celebration banner", async () => {
    const today = "2024-01-18";
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
        {
          id: "create_goal",
          title: "Goal",
          type: "once",
          commentary: "",
          completed: false,
        },
      ],
      xp: 10,
      streak: 1,
      daily_totals: { [today]: { completed: 1, total: 2 } },
      today,
    });

    render(<Trail />);

    expect(
      await screen.findByRole("heading", { name: en.trail.title })
    ).toBeInTheDocument();

    const progressBar = await screen.findByRole("progressbar");
    expect(progressBar).toHaveAttribute("aria-valuenow", "1");
    expect(progressBar).toHaveAttribute("aria-valuemax", "2");
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(screen.queryByText(en.trail.dailyComplete)).not.toBeInTheDocument();
    expect(screen.queryByText(en.trail.allDone)).not.toBeInTheDocument();
  });
});
