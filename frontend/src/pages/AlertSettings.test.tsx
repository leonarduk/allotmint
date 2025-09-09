import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { describe, it, expect, vi } from "vitest";
import i18n from "../i18n";
import Menu from "../components/Menu";
import AlertSettings from "./AlertSettings";

vi.mock("../api", () => ({
  getAlertThreshold: vi.fn().mockResolvedValue({ threshold: 5 }),
  setAlertThreshold: vi.fn().mockResolvedValue(undefined),
}));

vi.mock("../UserContext", () => ({
  useUser: () => ({ profile: { email: "user@example.com" } }),
}));

describe("AlertSettings", () => {
  it("renders translated strings", async () => {
    i18n.changeLanguage("fr");
    render(
      <MemoryRouter>
        <AlertSettings />
      </MemoryRouter>,
    );
    expect(
      await screen.findByRole("heading", { name: "Paramètres d'alerte" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Enregistrer" })).toBeInTheDocument();
    i18n.changeLanguage("en");
  });

  it("navigates to alert settings via menu", async () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={<Menu />} />
          <Route path="/alert-settings" element={<AlertSettings />} />
        </Routes>
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByLabelText(/menu/i));
    fireEvent.click(screen.getByRole("link", { name: "Alert Settings" }));
    expect(
      await screen.findByRole("heading", { name: "Alert Settings" }),
    ).toBeInTheDocument();
  });
});

