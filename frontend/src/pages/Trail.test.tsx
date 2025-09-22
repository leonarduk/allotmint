import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { axe } from "jest-axe";
import Trail from "./Trail";
import * as api from "../api";
import type { TrailResponse } from "../types";

vi.mock("../api");

const mockGetTrailTasks = vi.mocked(api.getTrailTasks);
const mockCompleteTrailTask = vi.mocked(api.completeTrailTask);

describe("Trail page", () => {
  const baseResponse: TrailResponse = {
    tasks: [
      {
        id: "check_market",
        title: "Check market overview",
        type: "daily",
        commentary: "",
        completed: false,
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
    ],
    xp: 0,
    streak: 0,
    today_completed: 0,
    today_total: 2,
    daily_totals: {},
  };

  it("renders progress summary and streak badge", async () => {
    mockGetTrailTasks.mockResolvedValueOnce(baseResponse);

    const { container } = render(<Trail />);

    await screen.findByText("Check market overview");

    expect(screen.getByText("XP: 0")).toBeInTheDocument();
    expect(screen.getByText(/No streak yet/i)).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "0");

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("celebrates when all daily tasks are completed", async () => {
    const initial: TrailResponse = {
      ...baseResponse,
      today_completed: 1,
      tasks: [
        { ...baseResponse.tasks[0], completed: false },
        { ...baseResponse.tasks[1], completed: true },
        baseResponse.tasks[2],
      ],
    };
    const completed: TrailResponse = {
      ...baseResponse,
      xp: 35,
      streak: 1,
      today_completed: 2,
      tasks: [
        { ...baseResponse.tasks[0], completed: true },
        { ...baseResponse.tasks[1], completed: true },
        baseResponse.tasks[2],
      ],
      daily_totals: {
        [new Date().toISOString().slice(0, 10)]: 2,
      },
    };

    mockGetTrailTasks.mockResolvedValueOnce(initial);
    mockCompleteTrailTask.mockResolvedValueOnce(completed);

    render(<Trail />);

    const action = await screen.findByRole("button", { name: "Check market overview" });
    fireEvent.click(action);

    expect(mockCompleteTrailTask).toHaveBeenCalledWith("check_market");
    await screen.findByText(/All daily tasks complete!/i);
    expect(screen.getByText("XP: 35")).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "100");
  });
});
