import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { describe, it, expect, vi } from "vitest";
import i18n from "../i18n";
import Menu from "../components/Menu";
import AlertSettings from "./AlertSettings";
import en from "../locales/en/translation.json";

vi.mock("../api", () => ({
  getAlertThreshold: vi.fn().mockResolvedValue({ threshold: 5 }),
  setAlertThreshold: vi.fn().mockResolvedValue({}),
}));

describe("AlertSettings navigation", () => {
  it("navigates from menu and shows translated strings", async () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={<Menu />} />
          <Route path="/alert-settings" element={<AlertSettings />} />
        </Routes>
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole("button", { name: i18n.t("app.menu") }));
    fireEvent.click(
      screen.getByRole("link", { name: i18n.t("app.modes.alertsettings") }),
    );
    expect(
      await screen.findByRole("heading", { name: en.alertSettings.title }),
    ).toBeInTheDocument();
    expect(
      screen.getByLabelText(new RegExp(en.alertSettings.threshold)),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: en.alertSettings.save }),
    ).toBeInTheDocument();
    expect(screen.getByText(en.alertSettings.description)).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: en.alertSettings.push.title })
    ).toBeInTheDocument();
  });
});
