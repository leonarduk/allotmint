import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi } from "vitest";
import i18n from "../i18n";
import Menu from "./Menu";

describe("Menu", () => {
  it("hides links by default and shows them after toggle", () => {
    render(
      <MemoryRouter>
        <Menu />
      </MemoryRouter>,
    );
    expect(screen.queryByRole("link", { name: "Logs" })).not.toBeInTheDocument();
    const toggle = screen.getByRole("button", { name: /menu/i });
    fireEvent.click(toggle);
    expect(screen.getByRole("link", { name: "Logs" })).toBeInTheDocument();
  });

  it("renders logout button when callback provided", () => {
    const onLogout = vi.fn();
    i18n.changeLanguage("fr");
    render(
      <MemoryRouter>
        <Menu onLogout={onLogout} />
      </MemoryRouter>,
    );
    const toggle = screen.getByRole("button", { name: /menu/i });
    fireEvent.click(toggle);
    const btn = screen.getByRole("button", { name: "Déconnexion" });
    fireEvent.click(btn);
    expect(onLogout).toHaveBeenCalled();
    i18n.changeLanguage("en");
  });
});
