import { renderHook, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { useAlertIdentity } from "@/hooks/useAlertIdentity";
import type { OwnerSummary } from "@/types";

const mockGetOwners = vi.hoisted(() => vi.fn());
const mockGetConfig = vi.hoisted(() => vi.fn());
const mockUseUser = vi.hoisted(() => vi.fn());

vi.mock("@/api", () => ({
  getOwners: mockGetOwners,
  getConfig: mockGetConfig,
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
  mockGetConfig.mockReset().mockResolvedValue(DISABLE_AUTH_DEMO_CONFIG);
  mockUseUser
    .mockReset()
    .mockReturnValue({ profile: undefined, setProfile: vi.fn() });
});

describe("useAlertIdentity identity resolution", () => {
  it("resolves to the demo identity when auth is disabled and no profile is set", async () => {
    const { result } = renderHook(() => useAlertIdentity());

    await waitFor(() => expect(result.current.resolving).toBe(false));
    expect(result.current.identity).toBe("demo");
    expect(result.current.displayOwner).toBe("demo");
    expect(result.current.forbidden).toBe(false);
    expect(result.current.saveDisabled).toBe(false);
  });

  it("uses the authenticated profile's email over the demo identity", async () => {
    mockUseUser.mockReturnValue({
      profile: { email: "alice@example.com" },
      setProfile: vi.fn(),
    });
    mockGetOwners.mockResolvedValue([
      { owner: "alice", full_name: "Alice", email: "alice@example.com", accounts: [] },
    ]);

    const { result } = renderHook(() => useAlertIdentity());

    await waitFor(() => expect(result.current.resolving).toBe(false));
    expect(result.current.identity).toBe("alice@example.com");
    // Display maps the identity back to the owner it belongs to.
    expect(result.current.displayOwner).toBe("Alice");
  });

  it("prefers local_login_email over demo_identity when auth is disabled and no profile is set", async () => {
    mockGetConfig.mockResolvedValue({
      disable_auth: true,
      local_login_email: "bob@example.com",
      demo_identity: "demo",
    });

    const { result } = renderHook(() => useAlertIdentity());

    await waitFor(() => expect(result.current.resolving).toBe(false));
    expect(result.current.identity).toBe("bob@example.com");
  });

  it("ignores the `?owner=` scope hint entirely: it must never name the wrong person", async () => {
    // ?owner= is a portfolio-scope hint left over from wherever the user
    // navigated from -- it has no relationship to the resolved identity.
    // Regression check for review round 3: the resolved identity must key
    // off `identity` ("demo" here), never off this query param, even though
    // a real owner named "lucy" exists and would otherwise look like a
    // plausible match.
    mockGetOwners.mockResolvedValue([
      { owner: "lucy", full_name: "Lucy Leonard", accounts: [] },
    ]);

    const { result } = renderHook(() => useAlertIdentity());

    await waitFor(() => expect(result.current.resolving).toBe(false));
    expect(result.current.identity).toBe("demo");
    expect(result.current.displayOwner).toBe("demo");
    expect(result.current.displayOwner).not.toBe("Lucy Leonard");
  });

  it("resolves to an empty identity and disables Save when auth is enabled and nobody is signed in", async () => {
    mockGetConfig.mockResolvedValue({
      disable_auth: false,
      local_login_email: null,
    });

    const { result } = renderHook(() => useAlertIdentity());

    await waitFor(() => expect(result.current.resolving).toBe(false));
    expect(result.current.identity).toBe("");
    expect(result.current.saveDisabled).toBe(true);
  });

  it("stays in the resolving state until config and owners have both settled", async () => {
    const configDeferred = deferred<typeof DISABLE_AUTH_DEMO_CONFIG>();
    mockGetConfig.mockReturnValue(configDeferred.promise);
    const ownersDeferred = deferred<OwnerSummary[]>();
    mockGetOwners.mockReturnValue(ownersDeferred.promise);

    const { result } = renderHook(() => useAlertIdentity());

    expect(result.current.resolving).toBe(true);
    expect(result.current.saveDisabled).toBe(true);

    configDeferred.resolve(DISABLE_AUTH_DEMO_CONFIG);
    ownersDeferred.resolve([]);

    await waitFor(() => expect(result.current.resolving).toBe(false));
    expect(result.current.identity).toBe("demo");
  });
});

describe("useAlertIdentity forbidden state", () => {
  it("exposes setForbidden and reflects it in saveDisabled", async () => {
    const { result } = renderHook(() => useAlertIdentity());

    await waitFor(() => expect(result.current.resolving).toBe(false));
    expect(result.current.forbidden).toBe(false);
    expect(result.current.saveDisabled).toBe(false);

    result.current.setForbidden(true);

    await waitFor(() => expect(result.current.forbidden).toBe(true));
    expect(result.current.saveDisabled).toBe(true);
  });
});
