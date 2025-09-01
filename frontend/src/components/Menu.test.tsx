import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Menu from "./Menu";

describe("Menu", () => {
  it("renders Logs tab", () => {
    render(
      <MemoryRouter>
        <Menu />
      </MemoryRouter>,
    );
    expect(screen.getByRole("link", { name: "Logs" })).toBeInTheDocument();
  });
});
