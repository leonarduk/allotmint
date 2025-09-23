import "../setupTests";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import type { ReactElement } from "react";
import { I18nextProvider, initReactI18next } from "react-i18next";
import { createInstance } from "i18next";
import en from "../locales/en/translation.json";

import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, afterEach } from "vitest";

const mockGetOwners = vi.hoisted(() => vi.fn());
const mockGetPensionForecast = vi.hoisted(() => vi.fn());

vi.mock("../api", () => ({
  getOwners: mockGetOwners,
  getPensionForecast: mockGetPensionForecast,
}));

function renderWithI18n(ui: ReactElement) {
  const i18n = createInstance();
  i18n.use(initReactI18next).init({
    lng: "en",
    resources: { en: { translation: en } },
  });
  return render(<I18nextProvider i18n={i18n}>{ui}</I18nextProvider>);
}

describe("PensionForecast page", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("renders owner selector and sliders", async () => {
    mockGetOwners.mockResolvedValue([{ owner: "alex", accounts: [] }]);
    mockGetPensionForecast.mockResolvedValue({
      forecast: [],
      projected_pot_gbp: 0,
      pension_pot_gbp: 0,
      current_age: 30,
      retirement_age: 65,
      dob: "1990-01-01",
    });

    const { default: PensionForecast } = await import("./PensionForecast");

    renderWithI18n(<PensionForecast />);

    const nowHeading = await screen.findByRole("heading", { name: /now/i });
    expect(nowHeading).toBeInTheDocument();

    const ownerSelect = await screen.findByLabelText(/owner/i);
    expect(ownerSelect).toBeInTheDocument();

    const careerSlider = screen.getByLabelText(/career path/i) as HTMLInputElement;
    expect(careerSlider).toHaveAttribute("type", "range");

    const spendingSlider = screen.getByLabelText(/monthly spending/i) as HTMLInputElement;
    expect(spendingSlider).toHaveAttribute("type", "range");

    const savingsSlider = screen.getByLabelText(/monthly contribution/i) as HTMLInputElement;
    expect(savingsSlider).toHaveAttribute("type", "range");
  });

  it("submits with selected owner", async () => {
    mockGetOwners.mockResolvedValue([
      { owner: "alex", accounts: [] },
      { owner: "beth", accounts: [] },
    ]);
    mockGetPensionForecast.mockResolvedValue({
      forecast: [],
      projected_pot_gbp: 200,
      pension_pot_gbp: 123,
      current_age: 30,
      retirement_age: 65,
      dob: "1990-01-01",
    });

    const { default: PensionForecast } = await import("./PensionForecast");

    renderWithI18n(<PensionForecast />);

    await screen.findByText("beth");
    const ownerSelect = await screen.findByLabelText(/owner/i);
    await userEvent.selectOptions(ownerSelect, "beth");

    const careerSlider = screen.getByLabelText(/career path/i) as HTMLInputElement;
    fireEvent.change(careerSlider, { target: { value: "2" } });

    const spendingSlider = screen.getByLabelText(/monthly spending/i) as HTMLInputElement;
    fireEvent.change(spendingSlider, { target: { value: "3000" } });

    const savingsSlider = screen.getByLabelText(/monthly contribution/i) as HTMLInputElement;
    fireEvent.change(savingsSlider, { target: { value: "750" } });

    const statePensionInput = screen.getByLabelText(/state pension/i);
    fireEvent.change(statePensionInput, { target: { value: "9000" } });

    const btn = screen.getByRole("button", { name: /forecast/i });
    await userEvent.click(btn);

    await vi.waitFor(() =>
      expect(mockGetPensionForecast).toHaveBeenCalledWith(
        expect.objectContaining({
          owner: "beth",
          investmentGrowthPct: 7,
          contributionMonthly: 750,
          desiredIncomeAnnual: 36000,
          statePensionAnnual: 9000,
        }),
      ),
    );
    await screen.findByText(/birth date: 1990-01-01/i);
    await screen.findByText(/Pension pot/i);
    await screen.findByText(/£123.00/);
    await screen.findByText(/projected pot at 65/i);
    await screen.findByText(/£323.00/);
    await screen.findByRole("heading", { name: /future you/i });
  });
});

