import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { describe, it, expect, beforeEach, vi } from "vitest";
import i18n from "../i18n";
import Menu from "../components/Menu";
import AlertSettings from "./AlertSettings";

vi.mock("../api", () => ({
  getAlertThreshold: vi.fn(),
  setAlertThreshold: vi.fn(),
}));

beforeEach(async () => {
  await i18n.changeLanguage("en");
});

describe("AlertSettings page", () => {
  it("navigates to alert settings from menu", async () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={<Menu />} />
          <Route path="/alert-settings" element={<AlertSettings />} />
        </Routes>
      </MemoryRouter>
    );
    fireEvent.click(screen.getByRole("button", { name: /menu/i }));
    fireEvent.click(screen.getByRole("link", { name: /Alert Settings/i }));
    expect(
      await screen.findByRole("heading", { name: /Alert Settings/i })
    ).toBeInTheDocument();
  });

  it("renders translated strings", async () => {
    await i18n.changeLanguage("fr");
    render(
      <MemoryRouter initialEntries={["/alert-settings"]}>
        <AlertSettings />
      </MemoryRouter>
    );
    expect(
      screen.getByRole("heading", { name: "Paramètres d'alerte" })
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Enregistrer" })).toBeInTheDocument();
    await i18n.changeLanguage("en");
  });
});

