import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import i18n from "@/i18n";
import Menu from "@/components/Menu";
import AlertSettings from "@/pages/AlertSettings";
import en from "@/locales/en/translation.json";
import type { OwnerSummary } from "@/types";

const mockGetOwners = vi.hoisted(() => vi.fn());
const mockGetAlertThreshold = vi.hoisted(() => vi.fn());
const mockSetAlertThreshold = vi.hoisted(() => vi.fn());
const mockGetConfig = vi.hoisted(() => vi.fn());
const mockUseUser = vi.hoisted(() => vi.fn());

vi.mock("@/api", () => ({
  getOwners: mockGetOwners,
  getAlertThreshold: mockGetAlertThreshold,
  setAlertThreshold: mockSetAlertThreshold,
  getConfig: mockGetConfig,
  getAlerts: vi.fn().mockResolvedValue([]),
  getNudges: vi.fn().mockResolvedValue([]),
  searchInstruments: vi.fn().mockResolvedValue([]),
}));

vi.mock("@/UserContext", () => ({
  useUser: mockUseUser,
}));

// Mirrors this repo's checked-in config.yaml: disable_auth true, demo_identity
// "demo", local_login_email unset. The backend resolves identity to "demo" in
// this shape regardless of which owner's portfolio is being viewed (#7225).
const DISABLE_AUTH_DEMO_CONFIG = {
  disable_auth: true,
  local_login_email: "",
  demo_identity: "demo",
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

beforeEach(() => {
  mockGetOwners.mockReset().mockResolvedValue([]);
  mockGetAlertThreshold.mockReset().mockResolvedValue({ threshold: 5 });
  mockSetAlertThreshold.mockReset().mockResolvedValue({ threshold: 5 });
  mockGetConfig.mockReset().mockResolvedValue(DISABLE_AUTH_DEMO_CONFIG);
  mockUseUser
    .mockReset()
    .mockReturnValue({ profile: undefined, setProfile: vi.fn() });
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
      screen.getByLabelText(new RegExp(en.alertSettings.threshold)),
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
    // Push has no implementation anywhere in this app -- the copy must say
    // so plainly rather than implying a browser-capability check (#7207).
    expect(
      screen.getByText(en.alertSettings.push.notSupported),
    ).toBeInTheDocument();

    // No profile and no owner in this deployment's /owners list has an email
    // matching the resolved identity, so the backend call -- and the API path
    // segment -- must be the demo identity from GET /config, never a
    // portfolio owner slug like "alice" (that always 403s; #7225 review).
    await waitFor(() => expect(mockGetAlertThreshold).toHaveBeenCalledWith("demo"));
    expect(
      screen.getByRole("button", { name: en.alertSettings.save }),
    ).toBeEnabled();
    expect(
      screen.getByText(
        i18n.t("alertSettings.managingFor", { owner: "demo" }),
      ),
    ).toBeInTheDocument();

    // Header parity (#5736): the shared AppHeader controls must be present,
    // not just the bare nav.
    expect(
      screen.getByRole("button", { name: "notifications" }),
    ).toBeInTheDocument();
    expect(screen.getByAltText("user avatar")).toBeInTheDocument();
  });
});

describe("AlertSettings identity resolution", () => {
  it("uses the authenticated profile's email over the demo identity (regression: this used to be the only working case)", async () => {
    mockUseUser.mockReturnValue({
      profile: { email: "alice@example.com" },
      setProfile: vi.fn(),
    });
    mockGetOwners.mockResolvedValue([
      { owner: "alice", full_name: "Alice", email: "alice@example.com", accounts: [] },
    ]);

    render(
      <MemoryRouter initialEntries={["/alert-settings"]}>
        <AlertSettings />
      </MemoryRouter>,
    );

    await waitFor(() =>
      expect(mockGetAlertThreshold).toHaveBeenCalledWith("alice@example.com"),
    );
    expect(
      screen.getByRole("button", { name: en.alertSettings.save }),
    ).toBeEnabled();
    // Display maps the identity back to the owner it belongs to.
    expect(
      screen.getByText(i18n.t("alertSettings.managingFor", { owner: "Alice" })),
    ).toBeInTheDocument();
  });

  it("prefers local_login_email over demo_identity when auth is disabled and no profile is set", async () => {
    mockGetConfig.mockResolvedValue({
      disable_auth: true,
      local_login_email: "bob@example.com",
      demo_identity: "demo",
    });

    render(
      <MemoryRouter initialEntries={["/alert-settings"]}>
        <AlertSettings />
      </MemoryRouter>,
    );

    await waitFor(() =>
      expect(mockGetAlertThreshold).toHaveBeenCalledWith("bob@example.com"),
    );
  });

  it("ignores the `?owner=` scope hint entirely: it must never name the wrong person as who this setting is for", async () => {
    // ?owner= is a portfolio-scope hint left over from wherever the user
    // navigated from -- it has no relationship to the resolved identity.
    // Regression check for review round 3: the API call and the on-screen
    // "Managing this setting for X" label must both key off `identity`
    // ("demo" here), never off this query param, even though a real owner
    // named "lucy" exists and would otherwise look like a plausible match.
    mockGetOwners.mockResolvedValue([
      { owner: "lucy", full_name: "Lucy Leonard", accounts: [] },
    ]);

    render(
      <MemoryRouter initialEntries={["/alert-settings?owner=lucy"]}>
        <AlertSettings />
      </MemoryRouter>,
    );

    await waitFor(() => expect(mockGetAlertThreshold).toHaveBeenCalledWith("demo"));
    expect(
      screen.getByText(i18n.t("alertSettings.managingFor", { owner: "demo" })),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(
        i18n.t("alertSettings.managingFor", { owner: "Lucy Leonard" }),
      ),
    ).not.toBeInTheDocument();
  });

  it("shows the sign-in notice and disables Save when auth is enabled and nobody is signed in", async () => {
    mockGetConfig.mockResolvedValue({
      disable_auth: false,
      local_login_email: null,
    });

    render(
      <MemoryRouter initialEntries={["/alert-settings"]}>
        <AlertSettings />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText(en.alertSettings.signInNotice),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: en.alertSettings.save }),
    ).toBeDisabled();
    expect(mockGetAlertThreshold).not.toHaveBeenCalled();
  });

  it("shows a resolving state instead of flashing the sign-in notice while config/owners are still loading", async () => {
    const configDeferred = deferred<typeof DISABLE_AUTH_DEMO_CONFIG>();
    mockGetConfig.mockReturnValue(configDeferred.promise);
    const ownersDeferred = deferred<OwnerSummary[]>();
    mockGetOwners.mockReturnValue(ownersDeferred.promise);

    render(
      <MemoryRouter initialEntries={["/alert-settings"]}>
        <AlertSettings />
      </MemoryRouter>,
    );

    expect(screen.getByText(en.alertSettings.resolving)).toBeInTheDocument();
    expect(
      screen.queryByText(en.alertSettings.signInNotice),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: en.alertSettings.save }),
    ).toBeDisabled();

    configDeferred.resolve(DISABLE_AUTH_DEMO_CONFIG);
    ownersDeferred.resolve([]);

    await waitFor(() => expect(mockGetAlertThreshold).toHaveBeenCalledWith("demo"));
    expect(
      screen.queryByText(en.alertSettings.resolving),
    ).not.toBeInTheDocument();
  });
});

describe("AlertSettings authorisation errors", () => {
  it("shows a specific notice and disables Save when the initial GET rejects the identity (403)", async () => {
    mockGetAlertThreshold.mockRejectedValue(
      Object.assign(new Error("Owner mismatch"), { status: 403 }),
    );

    render(
      <MemoryRouter initialEntries={["/alert-settings"]}>
        <AlertSettings />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText(
        i18n.t("alertSettings.forbiddenNotice", { owner: "demo" }),
      ),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(en.alertSettings.signInNotice),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: en.alertSettings.save }),
    ).toBeDisabled();
  });

  it("shows the specific notice and disables Save when the POST/save call itself rejects (403)", async () => {
    mockSetAlertThreshold.mockRejectedValue(
      Object.assign(new Error("Owner mismatch"), { status: 403 }),
    );

    render(
      <MemoryRouter initialEntries={["/alert-settings"]}>
        <AlertSettings />
      </MemoryRouter>,
    );

    const saveButton = await screen.findByRole("button", {
      name: en.alertSettings.save,
    });
    await waitFor(() => expect(saveButton).toBeEnabled());
    fireEvent.click(saveButton);

    expect(
      await screen.findByText(
        i18n.t("alertSettings.forbiddenNotice", { owner: "demo" }),
      ),
    ).toBeInTheDocument();
    expect(saveButton).toBeDisabled();
    expect(screen.queryByText(en.alertSettings.status.error)).not.toBeInTheDocument();
  });

  it("falls through to the generic error status on a 500 from save, not the forbidden notice", async () => {
    mockSetAlertThreshold.mockRejectedValue(
      Object.assign(new Error("Internal Server Error"), { status: 500 }),
    );

    render(
      <MemoryRouter initialEntries={["/alert-settings"]}>
        <AlertSettings />
      </MemoryRouter>,
    );

    const saveButton = await screen.findByRole("button", {
      name: en.alertSettings.save,
    });
    await waitFor(() => expect(saveButton).toBeEnabled());
    fireEvent.click(saveButton);

    expect(
      await screen.findByText(en.alertSettings.status.error),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(
        i18n.t("alertSettings.forbiddenNotice", { owner: "demo" }),
      ),
    ).not.toBeInTheDocument();
    // A 500 isn't an authorisation problem, so Save stays usable.
    expect(saveButton).toBeEnabled();
  });
});
