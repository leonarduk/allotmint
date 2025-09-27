import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { describe, it, expect, vi } from "vitest";
import i18n from "@/i18n";
import Menu from "@/components/Menu";
import AlertSettings from "@/pages/AlertSettings";
import en from "@/locales/en/translation.json";

vi.mock("@/api", () => ({
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
    fireEvent.click(screen.getByRole("button", {
      name: i18n.t("app.menuCategories.preferences"),
    }));
    const alertSettingsLink = await screen.findByRole("menuitem", { name: i18n.t("app.modes.alertsettings") });
    fireEvent.click(alertSettingsLink);
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

describe("AlertSettings when not signed in", () => {
  it("shows notice and disables buttons without a profile", async () => {
    // Mock Push API support so the push button renders
    Object.defineProperty(window, "PushManager", {
      value: {},
      configurable: true,
    });
    Object.defineProperty(navigator, "serviceWorker", {
      value: {
        ready: Promise.resolve({
          pushManager: { getSubscription: () => Promise.resolve(null) },
        }),
      },
      configurable: true,
    });

    render(
      <MemoryRouter>
        <AlertSettings />
      </MemoryRouter>,
    );

    expect(
      screen.getByText(en.alertSettings.signInNotice),
    ).toBeInTheDocument();

    const saveButton = screen.getByRole("button", {
      name: en.alertSettings.save,
    });
    expect(saveButton).toBeDisabled();

    const pushButton = await screen.findByRole("button", {
      name: en.alertSettings.push.enable,
    });
    expect(pushButton).toBeDisabled();
  });
});
