import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { describe, it, expect, vi } from "vitest";
import i18n from "@/i18n";
import Menu from "@/components/Menu";
import AlertSettings from "@/pages/AlertSettings";
import en from "@/locales/en/translation.json";
import { AuthContext } from "@/AuthContext";

vi.mock("@/api", () => ({
  getAlertThreshold: vi.fn().mockResolvedValue({ threshold: 5 }),
  setAlertThreshold: vi.fn().mockResolvedValue({}),
  getAlerts: vi.fn().mockResolvedValue([]),
  getNudges: vi.fn().mockResolvedValue([]),
  searchInstruments: vi.fn().mockResolvedValue([]),
}));

const mockUseUser = vi.hoisted(() =>
  vi.fn(() => ({ profile: undefined as { email: string } | undefined })),
);

vi.mock("@/UserContext", async () => {
  const actual =
    await vi.importActual<typeof import("@/UserContext")>("@/UserContext");
  return {
    ...actual,
    useUser: mockUseUser,
  };
});

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

    // Header parity (#5736): the shared AppHeader controls must be present,
    // not just the bare nav.
    expect(
      screen.getByRole("button", { name: "notifications" }),
    ).toBeInTheDocument();
    expect(screen.getByAltText("user avatar")).toBeInTheDocument();
  });
});

describe("AlertSettings when not signed in", () => {
  it("shows notice and disables buttons without a profile", async () => {
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
    expect(
      screen.getByText(en.alertSettings.push.notSupported),
    ).toBeInTheDocument();
  });
});

describe("AlertSettings demoReadOnly (issue #7411)", () => {
  it("disables the save button during a demo-readonly session even with a profile", async () => {
    mockUseUser.mockReturnValue({ profile: { email: "alex@example.com" } });

    render(
      <AuthContext.Provider
        value={{
          user: null,
          setUser: vi.fn(),
          logout: null,
          setLogout: vi.fn(),
          demoReadOnly: true,
          setDemoReadOnly: vi.fn(),
        }}
      >
        <MemoryRouter>
          <AlertSettings />
        </MemoryRouter>
      </AuthContext.Provider>,
    );

    const saveButton = await screen.findByRole("button", {
      name: en.alertSettings.save,
    });
    expect(saveButton).toBeDisabled();
    expect(saveButton).toHaveAttribute("title");

    mockUseUser.mockReturnValue({ profile: undefined });
  });
});
