import { describe, expect, it, vi } from "vitest";
import { decodePathSegment, encodePathSegment } from "@/utils/urlUtils";

describe("encodePathSegment", () => {
  it("encodes spaces as %20", () => {
    expect(encodePathSegment("joe leonard")).toBe("joe%20leonard");
  });

  it("encodes special characters", () => {
    expect(encodePathSegment("owner/one")).toBe("owner%2Fone");
    expect(encodePathSegment("owner&one")).toBe("owner%26one");
  });

  it("trims leading and trailing whitespace before encoding", () => {
    expect(encodePathSegment("  alice  ")).toBe("alice");
    expect(encodePathSegment("  joe leonard  ")).toBe("joe%20leonard");
  });

  it("passes through plain ASCII slugs unchanged", () => {
    expect(encodePathSegment("alice")).toBe("alice");
    expect(encodePathSegment("alice-bob")).toBe("alice-bob");
  });

  it("does not double-encode already-encoded strings", () => {
    // encodePathSegment is called on raw owner values from state (decoded),
    // never on already-encoded strings. But verify the behaviour is predictable:
    // passing a pre-encoded string encodes the % sign itself.
    expect(encodePathSegment("joe%20leonard")).toBe("joe%2520leonard");
  });
});

describe("decodePathSegment", () => {
  it("decodes a percent-encoded space", () => {
    expect(decodePathSegment("joe%20leonard")).toBe("joe leonard");
  });

  it("returns plain ASCII slugs unchanged", () => {
    expect(decodePathSegment("alice")).toBe("alice");
  });

  it("returns the raw value for malformed percent sequences and warns", () => {
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
    // "%ZZ" is an invalid percent-encoded sequence
    expect(decodePathSegment("%ZZ")).toBe("%ZZ");
    expect(warnSpy).toHaveBeenCalledWith(
      "Failed to decode owner path segment; using raw value",
      expect.objectContaining({ segment: "%ZZ" }),
    );
    warnSpy.mockRestore();
  });

  it("decode is the inverse of encode for plain owner names", () => {
    const owners = ["alice", "joe leonard", "bob-smith", "owner one"];
    for (const owner of owners) {
      expect(decodePathSegment(encodePathSegment(owner))).toBe(owner);
    }
  });
});

describe("getOwnerRootRedirectPath URL encoding", () => {
  it("encodes owner names with spaces in the redirect path", async () => {
    const { getOwnerRootRedirectPath } = await import("@/App");
    const result = getOwnerRootRedirectPath("/portfolio", "", [
      { owner: "joe leonard", accounts: [] },
    ]);
    expect(result).toBe("/portfolio/joe%20leonard");
  });

  it("uses plain slugs unchanged in the redirect path", async () => {
    const { getOwnerRootRedirectPath } = await import("@/App");
    const result = getOwnerRootRedirectPath("/portfolio", "", [
      { owner: "alice", accounts: [] },
    ]);
    expect(result).toBe("/portfolio/alice");
  });

  it("uses the performance redirect path for /performance root", async () => {
    const { getOwnerRootRedirectPath } = await import("@/App");
    const result = getOwnerRootRedirectPath("/performance", "", [
      { owner: "alice", accounts: [] },
    ]);
    expect(result).toBe("/performance/alice");
  });
});
