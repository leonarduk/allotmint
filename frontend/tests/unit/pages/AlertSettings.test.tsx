import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import i18n from "@/i18n";
import Menu from "@/components/Menu";
import AlertSettings from "@/pages/AlertSettings";
import en from "@/locales/en/translation.json";

const mockGetOwners = vi.hoisted(() => vi.fn());
const mockGetAlertThreshold = vi.hoisted(() => vi.fn());
const mockSetAlertThreshold = vi.hoisted(() => vi.fn());

vi.mock("@/api", () => ({
  getOwners: mockGetOwners,
  getAlertThreshold: mockGetAlertThreshold,
  setAlertThreshold: mockSetAlertThreshold,
  getAlerts: vi.fn().mockResolvedValue([]),
  getNudges: vi.fn().mockResolvedValue([]),
  searchInstruments: vi.fn().mockResolvedValue([]),
}));

beforeEach(() => {
  mockGetOwners.mockReset().mockResolvedValue([]);
  mockGetAlertThreshold.mockReset().mockResolvedValue({ threshold: 5 });
  mockSetAlertThreshold.mockReset().mockResolvedValue({ threshold: 5 });
});

describe("AlertSettings navigation", () => {
  it("navigates from menu and shows translated strings", async () => {
    mockGetOwners.mockResolvedValue([
      { owner: "alice", full_name: "Alice", accounts: [] },
    ]);
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
      screen.getByLabelText(new RegExp(en.alertSettings.threshold.prefix)),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: en.alertSettings.save }),
    ).toBeInTheDocument();
    expect(screen.getByText(en.alertSettings.description)).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: en.alertSettings.viewAlertsLink }),
    ).toHaveAttribute("href", "/alerts");
    expect(
      screen.getByRole("heading", { name: en.alertSettings.push.title })
    ).toBeInTheDocument();

    // Owner falls back to the first entry from /owners (like other pages,
    // e.g. PensionForecast) since no owner was pre-selected, so the page is
    // usable without an authenticated profile (#7225).
    await waitFor(() => expect(mockGetAlertThreshold).toHaveBeenCalledWith("alice"));
    expect(
      screen.getByRole("button", { name: en.alertSettings.save }),
    ).toBeEnabled();

    // Header parity (#5736): the shared AppHeader controls must be present,
    // not just the bare nav.
    expect(
      screen.getByRole("button", { name: "notifications" }),
    ).toBeInTheDocument();
    expect(screen.getByAltText("user avatar")).toBeInTheDocument();
  });
});

describe("AlertSettings owner resolution", () => {
  it("prefers the owner carried on the URL over the /owners fallback", async () => {
    mockGetOwners.mockResolvedValue([
      { owner: "amy", full_name: "Amy", accounts: [] },
    ]);
    render(
      <MemoryRouter initialEntries={["/alert-settings?owner=steve"]}>
        <AlertSettings />
      </MemoryRouter>,
    );

    await waitFor(() => expect(mockGetAlertThreshold).toHaveBeenCalledWith("steve"));
    // The /owners fallback is only used when there's no `?owner=`.
    expect(mockGetOwners).not.toHaveBeenCalled();
    expect(
      screen.getByRole("button", { name: en.alertSettings.save }),
    ).toBeEnabled();
  });

  it("shows a specific notice and disables Save when the backend rejects the owner (403)", async () => {
    mockGetAlertThreshold.mockRejectedValue(
      Object.assign(new Error("Owner mismatch"), { status: 403 }),
    );
    render(
      <MemoryRouter initialEntries={["/alert-settings?owner=mo"]}>
        <AlertSettings />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText(
        i18n.t("alertSettings.forbiddenNotice", { owner: "mo" }),
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText(en.alertSettings.signInNotice)).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: en.alertSettings.save }),
    ).toBeDisabled();
  });

  it("shows the sign-in notice and disables Save only when no owner can be resolved at all", async () => {
    mockGetOwners.mockResolvedValue([]);
    render(
      <MemoryRouter initialEntries={["/alert-settings"]}>
        <AlertSettings />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText(en.alertSettings.signInNotice),
    ).toBeInTheDocument();

    const saveButton = screen.getByRole("button", {
      name: en.alertSettings.save,
    });
    expect(saveButton).toBeDisabled();
    expect(
      screen.getByText(en.alertSettings.push.notSupported),
    ).toBeInTheDocument();
    expect(mockGetAlertThreshold).not.toHaveBeenCalled();
  });
});
