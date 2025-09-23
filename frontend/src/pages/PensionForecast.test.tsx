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

  it("renders banner metrics and owner selector", async () => {
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

    const form = document.querySelector("form")!;
    const ownerSelect = await within(form).findByLabelText(/owner/i);
    expect(ownerSelect).toBeInTheDocument();
    const selects = await screen.findAllByLabelText(/owner/i, {
      selector: 'select',
    });
    expect(selects[0]).toBeInTheDocument();

    expect(screen.getByTestId("pension-pot-amount")).toHaveTextContent("—");
    expect(screen.getByTestId("user-contribution-amount")).toHaveTextContent("£0.00");
    expect(screen.getByTestId("employer-contribution-amount")).toHaveTextContent("£0.00");
    const addBtn = screen.getByRole("button", { name: /add another pension/i });
    expect(addBtn).toBeInTheDocument();
    expect(
      screen.queryByText(/total monthly contributions/i),
    ).not.toBeInTheDocument();

    await userEvent.click(addBtn);
    expect(
      screen.getByTestId("additional-pension-notice"),
    ).toHaveTextContent("You have added 1 additional pension.");
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
    const form = document.querySelector("form")!;
    const ownerSelect = await within(form).findByLabelText(/owner/i);
    await userEvent.selectOptions(ownerSelect, "beth");

    const growth = within(form).getByLabelText(/growth assumption/i);
    await userEvent.selectOptions(growth, "7");

    fireEvent.change(ownerSelect, { target: { value: "beth" } });
    const monthly = within(form).getByLabelText(/^monthly contribution/i);
    fireEvent.change(monthly, { target: { value: "100" } });
    const employerMonthly = within(form).getByLabelText(/^employer monthly contribution/i);
    fireEvent.change(employerMonthly, { target: { value: "50" } });

    const btn = screen.getByRole("button", { name: /forecast/i });
    await userEvent.click(btn);

    await vi.waitFor(() =>
      expect(mockGetPensionForecast).toHaveBeenCalledWith(
        expect.objectContaining({
          owner: "beth",
          investmentGrowthPct: 7,
          contributionMonthly: 150,
        }),
      ),
    );
    await screen.findByText(/birth date: 1990-01-01/i);
    await screen.findByText(/pension pot: £123.00/i);
    await screen.findByText(/projected pot at 65: £323.00/i);
    expect(screen.getByTestId("pension-pot-amount")).toHaveTextContent("£123.00");
    expect(screen.getByTestId("user-contribution-amount")).toHaveTextContent("£100.00");
    expect(screen.getByTestId("employer-contribution-amount")).toHaveTextContent(
      "£50.00",
    );
    expect(screen.getByText(/total monthly contributions: £150.00/i)).toBeInTheDocument();
  });
});

