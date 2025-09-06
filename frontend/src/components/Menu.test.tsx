import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi } from "vitest";
import i18n from "../i18n";
import Menu from "./Menu";

describe("Menu", () => {
  it("renders support link and no Logs tab by default", () => {
    render(
      <MemoryRouter>
        <Menu />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByLabelText("menu"));
    expect(screen.getByRole("link", { name: "Support" })).toHaveAttribute("href", "/support");
    expect(screen.queryByRole("link", { name: "Logs" })).not.toBeInTheDocument();
  });

  it("renders Logs tab in support mode", () => {
    render(
      <MemoryRouter initialEntries={["/support"]}>
        <Menu />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByLabelText("menu"));
    expect(screen.getByRole("link", { name: "Logs" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "App" })).toHaveAttribute("href", "/");
  });

  it("renders logout button when callback provided", () => {
    const onLogout = vi.fn();
    i18n.changeLanguage("fr");
    render(
      <MemoryRouter>
        <Menu onLogout={onLogout} />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByLabelText("menu"));
    const btn = screen.getByRole("button", { name: "Déconnexion" });
    fireEvent.click(btn);
    expect(onLogout).toHaveBeenCalled();
    i18n.changeLanguage("en");
  });
});
