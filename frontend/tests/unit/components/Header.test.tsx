import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { Header } from "@/components/Header";
import Menu from "@/components/Menu";
import { MemoryRouter } from "react-router-dom";
import { fireEvent } from "@testing-library/react";
import i18n from "@/i18n";
import { I18nextProvider } from "react-i18next";
import { formatDateISO } from "@/lib/date";

describe("Header", () => {
  it("shows localized as-of summary when data present", () => {
    render(
      <I18nextProvider i18n={i18n}>
        <Header asOf="2024-07-01" tradesThisMonth={3} tradesRemaining={17} />
      </I18nextProvider>,
    );
    expect(
      screen.getByText(
        `As of ${formatDateISO(new Date("2024-07-01"))} • Trades this month: 3 / 20 (Remaining: 17)`,
      ),
    ).toBeInTheDocument();
  });

  it("renders nothing without data", () => {
    const { container } = render(
      <I18nextProvider i18n={i18n}>
        <Header />
      </I18nextProvider>,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("toggles menu drawer", async () => {
    render(
      <MemoryRouter>
        <Menu />
      </MemoryRouter>
    );
    const settingsToggle = screen.getByRole("button", {
      name: i18n.t("app.menuCategories.preferences"),
    });
    fireEvent.click(settingsToggle);
    expect(await screen.findByRole("menuitem", { name: "Support" })).toBeInTheDocument();
  });
});
