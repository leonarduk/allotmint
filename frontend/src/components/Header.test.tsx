import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { Header } from "./Header";
import Menu from "./Menu";
import { MemoryRouter } from "react-router-dom";
import { fireEvent } from "@testing-library/react";
import i18n from "../i18n";

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

  it("toggles menu drawer", () => {
    render(
      <MemoryRouter>
        <Menu />
      </MemoryRouter>
    );
    const toggle = screen.getByLabelText(i18n.t("app.menu"));
    fireEvent.click(toggle);
    expect(screen.getByRole("link", { name: "Support" })).toBeInTheDocument();
  });
});
