import { render, screen, fireEvent } from "@testing-library/react";
import type { ReactElement } from "react";
import { I18nextProvider, initReactI18next } from "react-i18next";
import { createInstance } from "i18next";
import en from "../locales/en/translation.json";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";

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
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders owner selector", async () => {
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

    const [ownerSelect] = await screen.findAllByLabelText(/owner/i);
    expect(ownerSelect).toBeInTheDocument();
    const selects = await screen.findAllByLabelText(/owner/i, {
      selector: 'select',
    });
    expect(selects[0]).toBeInTheDocument();
  });

  it("submits with selected owner", async () => {
    mockGetOwners.mockResolvedValue([
      { owner: "alex", accounts: [] },
      { owner: "beth", accounts: [] },
    ]);
    mockGetPensionForecast.mockResolvedValue({
      forecast: [],
      projected_pot_gbp: 0,
      pension_pot_gbp: 123,
      current_age: 30,
      retirement_age: 65,
      dob: "1990-01-01",
    });

    const { default: PensionForecast } = await import("./PensionForecast");

    renderWithI18n(<PensionForecast />);

    const [select] = await screen.findAllByLabelText(/owner/i, {
      selector: 'select',
    });
    await userEvent.selectOptions(select, "beth");

    const growth = screen.getByLabelText(/growth assumption/i);
    await userEvent.selectOptions(growth, "7");

    const [ownerSelect] = await screen.findAllByLabelText(/owner/i);
    fireEvent.change(ownerSelect, { target: { value: "beth" } });
    const monthly = screen.getByLabelText(/monthly contribution/i);
    fireEvent.change(monthly, { target: { value: "100" } });

    const btn = screen.getByRole("button", { name: /forecast/i });
    await userEvent.click(btn);

    await vi.waitFor(() =>
      expect(mockGetPensionForecast).toHaveBeenCalledWith(
        expect.objectContaining({
          owner: "beth",
          investmentGrowthPct: 7,
          contributionMonthly: 100,
        }),
      ),
    );
    await screen.findByText(/birth date: 1990-01-01/i);
    await screen.findByText(/pension pot: £123.00/i);
  });
});

