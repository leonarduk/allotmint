import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { Header } from "@/components/Header";
import Menu from "@/components/Menu";
import { MemoryRouter } from "react-router-dom";
import { fireEvent } from "@testing-library/react";
import i18n from "@/i18n";

describe("Header", () => {
  it("shows trade meter when data present", () => {
    render(<Header tradesThisMonth={3} tradesRemaining={17} />);
    expect(
      screen.getByText(/Trades this month: 3 \/ 20 \(Remaining: 17\)/)
    ).toBeInTheDocument();
  });

  it("renders nothing without data", () => {
    const { container } = render(<Header />);
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
