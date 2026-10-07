import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, afterEach } from "vitest";
import * as api from "@/api";
import { PricingAsOf } from "@/components/PricingAsOf";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("PricingAsOf", () => {
  it("shows only the date when pricing is current", () => {
    render(
      <PricingAsOf
        pricingDate="2026-09-18"
        historical={false}
        onRefreshed={vi.fn()}
        today="2026-09-21"
      />,
    );
    expect(screen.getByText("Pricing as of 2026-09-18")).toBeInTheDocument();
    expect(screen.queryByRole("status")).toBeNull();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("flags stale pricing with its age and refreshes on demand", async () => {
    const refresh = vi
      .spyOn(api, "refreshPrices")
      .mockResolvedValue({ status: "ok", tickers: 3 });
    const onRefreshed = vi.fn();
    render(
      <PricingAsOf
        pricingDate="2026-09-18"
        historical={false}
        onRefreshed={onRefreshed}
        today="2026-09-22"
      />,
    );
    expect(screen.getByRole("status")).toHaveTextContent("Prices are 4 days old");

    await userEvent.click(screen.getByRole("button", { name: "Refresh Prices" }));

    await waitFor(() => expect(onRefreshed).toHaveBeenCalledTimes(1));
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it("explains a failed refresh instead of reloading", async () => {
    vi.spyOn(api, "refreshPrices").mockRejectedValue(new Error("offline"));
    const onRefreshed = vi.fn();
    render(
      <PricingAsOf
        pricingDate="2026-09-18"
        historical={false}
        onRefreshed={onRefreshed}
        today="2026-09-22"
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: "Refresh Prices" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Couldn’t refresh prices: offline",
    );
    expect(onRefreshed).not.toHaveBeenCalled();
  });

  it("never flags a deliberately chosen historical date", () => {
    render(
      <PricingAsOf
        pricingDate="2024-04-01"
        historical
        onRefreshed={vi.fn()}
        today="2026-09-22"
      />,
    );
    expect(screen.queryByRole("status")).toBeNull();
  });
});
