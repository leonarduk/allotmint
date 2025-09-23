import "../setupTests";
import { render, screen, within, fireEvent, cleanup } from "@testing-library/react";
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

  it("renders owner selector", async () => {
    mockGetOwners.mockResolvedValue([{ owner: "alex", accounts: [] }]);
    mockGetPensionForecast.mockResolvedValue({
      forecast: [],
      projected_pot_gbp: 0,
      pension_pot_gbp: 0,
      current_age: 30,
      retirement_age: 65,
      dob: "1990-01-01",
      earliest_retirement_age: null,
      retirement_income_breakdown: null,
      retirement_income_total_annual: null,
      desired_income_annual: null,
    });

    const { default: PensionForecast } = await import("./PensionForecast");

    renderWithI18n(<PensionForecast />);

    const form = document.querySelector("form")!;
    const ownerSelect = await within(form).findByLabelText(/owner/i);
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
      projected_pot_gbp: 200,
      pension_pot_gbp: 123,
      current_age: 30,
      retirement_age: 65,
      dob: "1990-01-01",
      earliest_retirement_age: 64,
      retirement_income_breakdown: {
        state_pension_annual: 9000,
        defined_benefit_annual: 4000,
        defined_contribution_annual: 2000,
      },
      retirement_income_total_annual: 15000,
      desired_income_annual: 14000,
      employer_contribution_monthly: 80,
    });

    const { default: PensionForecast } = await import("./PensionForecast");

    renderWithI18n(<PensionForecast />);

    expect(
      await screen.findByRole("button", { name: /add another pension/i }),
    ).toBeInTheDocument();
    expect(screen.getByText("Added pensions: 0")).toBeInTheDocument();

    await screen.findByText("beth");
    const form = document.querySelector("form")!;
    const ownerSelect = await within(form).findByLabelText(/owner/i);
    await userEvent.selectOptions(ownerSelect, "beth");

    const growth = within(form).getByLabelText(/growth assumption/i);
    await userEvent.selectOptions(growth, "7");

    fireEvent.change(ownerSelect, { target: { value: "beth" } });
    const monthly = within(form).getByLabelText(/monthly contribution/i);
    fireEvent.change(monthly, { target: { value: "100" } });
    const employer = within(form).getByLabelText(/employer contribution/i);
    fireEvent.change(employer, { target: { value: "75" } });

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
    await screen.findByText(/projected pot at 65: £323.00/i);
    await screen.findByText("Retirement income breakdown");
    expect(
      screen.getByText(
        "You're on track: projected income of £15,000.00 meets your desired £14,000.00 from age 64.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Your pension overview")).toBeInTheDocument();
    expect(screen.getByText("Current pension pot")).toBeInTheDocument();
    expect(screen.getByText("Your monthly contribution")).toBeInTheDocument();
    expect(screen.getByText("Employer contribution")).toBeInTheDocument();
    expect(screen.getByText("£100.00")).toBeInTheDocument();
    expect(screen.getByText("£80.00")).toBeInTheDocument();
    expect(screen.getByText("State pension")).toBeInTheDocument();
    expect(screen.getByText("Defined benefit")).toBeInTheDocument();
    expect(screen.getByText("Defined contribution")).toBeInTheDocument();
    expect(screen.getByText("£9,000.00")).toBeInTheDocument();
    expect(screen.getByText("£750.00")).toBeInTheDocument();
    expect(screen.getByText("60%", { exact: false })).toBeInTheDocument();
    expect(
      screen.getByText("Total annual income: £15,000.00", { exact: true }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Total monthly income: £1,250.00", { exact: true }),
    ).toBeInTheDocument();
  });

  it("shows shortfall insight when desired income is not met", async () => {
    mockGetOwners.mockResolvedValue([{ owner: "alex", accounts: [] }]);
    mockGetPensionForecast.mockResolvedValue({
      forecast: [],
      projected_pot_gbp: 50,
      pension_pot_gbp: 25,
      current_age: 40,
      retirement_age: 67,
      dob: "1984-01-01",
      earliest_retirement_age: null,
      retirement_income_breakdown: {
        state_pension_annual: 6000,
        defined_benefit_annual: 0,
        defined_contribution_annual: 1000,
      },
      retirement_income_total_annual: 7000,
      desired_income_annual: 12000,
    });

    const { default: PensionForecast } = await import("./PensionForecast");

    renderWithI18n(<PensionForecast />);

    const form = document.querySelector("form")!;
    const desired = within(form).getByLabelText(/desired income/i);
    fireEvent.change(desired, { target: { value: "12000" } });

    const btn = screen.getByRole("button", { name: /forecast/i });
    await userEvent.click(btn);

    await screen.findByText(
      "Projected income leaves a shortfall of £5,000.00 per year (£416.67 per month) against your desired £12,000.00.",
    );
  });

  it("increments added pension count from the summary banner", async () => {
    mockGetOwners.mockResolvedValue([{ owner: "alex", accounts: [] }]);
    mockGetPensionForecast.mockResolvedValue({
      forecast: [],
      projected_pot_gbp: 0,
      pension_pot_gbp: 0,
      current_age: 30,
      retirement_age: 65,
      dob: "1990-01-01",
      earliest_retirement_age: null,
      retirement_income_breakdown: null,
      retirement_income_total_annual: null,
      desired_income_annual: null,
    });

    const { default: PensionForecast } = await import("./PensionForecast");

    renderWithI18n(<PensionForecast />);

    await screen.findByText("alex");

    const addButton = screen.getByRole("button", {
      name: /add another pension/i,
    });
    expect(screen.getByText("Added pensions: 0")).toBeInTheDocument();

    await userEvent.click(addButton);

    expect(screen.getByText("Added pensions: 1")).toBeInTheDocument();
  });
});

