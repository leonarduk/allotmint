import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, type Mock, beforeEach } from "vitest";
import i18n from "../i18n";

vi.mock("../api", () => ({ getInstrumentDetail: vi.fn() }));
import { getInstrumentDetail } from "../api";

class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(global as any).ResizeObserver = ResizeObserver;

import { InstrumentDetail } from "./InstrumentDetail";

describe("InstrumentDetail", () => {
  const mockGetInstrumentDetail = getInstrumentDetail as unknown as Mock;

  beforeEach(() => {
    mockGetInstrumentDetail.mockReset();
  });

  it.each(["en", "fr", "de", "es", "pt"]) (
    "links to timeseries edit page (%s)",
    async (lang) => {
      mockGetInstrumentDetail.mockResolvedValue({
        prices: [],
        positions: [],
        currency: null,
      });

      i18n.changeLanguage(lang);

      render(
        <MemoryRouter>
          <InstrumentDetail ticker="ABC.L" name="ABC" onClose={() => {}} />
        </MemoryRouter>,
      );
      const link = await screen.findByRole("link", {
        name: i18n.t("instrumentDetail.edit"),
      });
      expect(link).toHaveAttribute("href", "/timeseries?ticker=ABC&exchange=L");
      expect(screen.getByRole("heading", { name: "ABC" })).toBeInTheDocument();
      expect(screen.getByText(/ABC\.L/)).toBeInTheDocument();
    },
  );

  it("displays 7d and 30d changes", async () => {
    const prices = Array.from({ length: 30 }, (_, i) => ({
      date: `2024-01-${String(i + 1).padStart(2, "0")}`,
      close_gbp: 100,
    }));
    prices.push({ date: "2024-01-31", close_gbp: 130 });

    mockGetInstrumentDetail.mockResolvedValue({
      prices,
      positions: [],
      currency: null,
    });

    i18n.changeLanguage("en");

    render(
      <MemoryRouter>
        <InstrumentDetail ticker="ABC.L" name="ABC" onClose={() => {}} />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText(
        `${i18n.t("instrumentDetail.change7d")} 30.0%`,
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        `${i18n.t("instrumentDetail.change30d")} 30.0%`,
      ),
    ).toBeInTheDocument();
  });
});

