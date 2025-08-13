import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { I18nextProvider, initReactI18next } from "react-i18next";
import { createInstance } from "i18next";
import type { ReactElement } from "react";
import en from "../locales/en/translation.json";

vi.mock("../api", () => ({
  getScreener: vi.fn().mockResolvedValue([
    {
      ticker: "AAA",
      name: "Alpha",
      peg_ratio: 1,
      pe_ratio: 10,
      de_ratio: 0.5,
      fcf: 1000,
    },
  ]),
}));

import { Screener } from "./Screener";
import { getScreener } from "../api";

function renderWithI18n(ui: ReactElement) {
  const i18n = createInstance();
  i18n.use(initReactI18next).init({
    lng: "en",
    resources: { en: { translation: en } },
  });
  return render(<I18nextProvider i18n={i18n}>{ui}</I18nextProvider>);
}

describe("Screener page", () => {
  it("submits criteria and renders results", async () => {
    renderWithI18n(<Screener />);

    fireEvent.change(screen.getByLabelText(en.screener.tickers), {
      target: { value: "AAA" },
    });
    fireEvent.change(screen.getByLabelText(en.screener.maxPeg), {
      target: { value: "2" },
    });

    fireEvent.click(screen.getByRole("button", { name: en.screener.run }));

    expect(await screen.findByText("AAA")).toBeInTheDocument();
    expect(getScreener).toHaveBeenCalledWith(["AAA"], { peg_max: 2 });
  });
});

