import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { act } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import en from "@/locales/en/translation.json";
import DataQuality from "@/pages/DataQuality";

const mockGetDataQualityTimeseries = vi.hoisted(() => vi.fn());

vi.mock("@/api", async () => {
  const actual = await vi.importActual<typeof import("@/api")>("@/api");
  return {
    ...actual,
    getDataQualityTimeseries: mockGetDataQualityTimeseries,
  };
});

beforeEach(() => {
  (globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;
  vi.clearAllMocks();
});

describe("DataQuality page", () => {
  it("renders a row per position with counts and RAG status", async () => {
    mockGetDataQualityTimeseries.mockResolvedValue({
      count: 3,
      positions: [
        {
          ticker: "CLEAN",
          exchange: "L",
          total_points: 100,
          first_date: "2026-01-01",
          last_date: "2026-06-01",
          gap_count: 0,
          gaps: [],
          duplicate_dates: [],
          outliers: [],
        },
        {
          ticker: "GAPPY",
          exchange: "L",
          total_points: 50,
          first_date: "2026-01-01",
          last_date: "2026-06-01",
          gap_count: 1,
          gaps: [{ start: "2026-02-01", end: "2026-02-05", missing_business_days: 4 }],
          duplicate_dates: [],
          outliers: [],
        },
        {
          ticker: "DUPED",
          exchange: "N",
          total_points: 30,
          first_date: "2026-01-01",
          last_date: "2026-06-01",
          gap_count: 0,
          gaps: [],
          duplicate_dates: ["2026-03-01"],
          outliers: [{ date: "2026-04-01", value: 999, z_score: 5.2 }],
        },
      ],
    });

    render(<DataQuality />);

    expect(await screen.findByRole("heading", { name: en.dataQuality.title })).toBeInTheDocument();
    expect(await screen.findByText("CLEAN")).toBeInTheDocument();
    expect(screen.getByText("GAPPY")).toBeInTheDocument();
    expect(screen.getByText("DUPED")).toBeInTheDocument();

    expect(screen.getByText(en.dataQuality.status.green)).toBeInTheDocument();
    expect(screen.getByText(en.dataQuality.status.amber)).toBeInTheDocument();
    expect(screen.getByText(en.dataQuality.status.red)).toBeInTheDocument();
  });

  it("shows an empty state when no positions are cached", async () => {
    mockGetDataQualityTimeseries.mockResolvedValue({ count: 0, positions: [] });

    render(<DataQuality />);

    expect(await screen.findByText(en.dataQuality.noData)).toBeInTheDocument();
  });

  it("shows an error message when the request fails", async () => {
    mockGetDataQualityTimeseries.mockRejectedValueOnce(new Error("boom"));

    render(<DataQuality />);

    expect(await screen.findByText("boom")).toBeInTheDocument();
  });

  it("opens the drill-down modal with problematic dates for a position", async () => {
    mockGetDataQualityTimeseries.mockResolvedValue({
      count: 1,
      positions: [
        {
          ticker: "DUPED",
          exchange: "N",
          total_points: 30,
          first_date: "2026-01-01",
          last_date: "2026-06-01",
          gap_count: 1,
          gaps: [{ start: "2026-02-01", end: "2026-02-05", missing_business_days: 4 }],
          duplicate_dates: ["2026-03-01"],
          outliers: [{ date: "2026-04-01", value: 999, z_score: 5.2 }],
        },
      ],
    });

    render(<DataQuality />);

    const viewDetailsButton = await screen.findByRole("button", {
      name: en.dataQuality.viewDetailsFor
        .replace("{{ticker}}", "DUPED")
        .replace("{{exchange}}", "N"),
    });
    await act(async () => {
      await userEvent.click(viewDetailsButton);
    });

    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("2026-03-01");
    expect(dialog).toHaveTextContent("2026-04-01");
    expect(dialog).toHaveTextContent("2026-02-01");

    const closeButton = screen.getByRole("button", { name: en.dataQuality.drilldown.close });
    await act(async () => {
      await userEvent.click(closeButton);
    });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
