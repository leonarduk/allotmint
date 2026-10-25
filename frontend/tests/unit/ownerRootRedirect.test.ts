import { describe, expect, it } from "vitest";
import {
  getOwnerRootRedirectPath,
  getPerformanceRootRedirectPath,
} from "@/routes/ownerRootRedirect";

describe("getOwnerRootRedirectPath", () => {
  const owners = [{ owner: "alice", accounts: [] }];

  it("redirects portfolio root to first owner", () => {
    expect(getOwnerRootRedirectPath("/portfolio", "", owners)).toBe("/portfolio/alice");
  });

  it("redirects performance root to first owner when there are no groups", () => {
    expect(getOwnerRootRedirectPath("/performance", "", owners)).toBe("/performance/alice");
  });

  it("does not redirect when owner is already selected", () => {
    expect(getOwnerRootRedirectPath("/portfolio", "alice", owners)).toBeNull();
  });

  it("does not redirect when owners list is empty", () => {
    expect(getOwnerRootRedirectPath("/portfolio", "", [])).toBeNull();
  });

  it("does not redirect direct owner routes", () => {
    expect(getOwnerRootRedirectPath("/portfolio/alice", "alice", owners)).toBeNull();
    expect(getOwnerRootRedirectPath("/performance/alice", "alice", owners)).toBeNull();
  });

  describe("performance group scope (#7228)", () => {
    it("does not redirect /performance?group=all onto an owner", () => {
      expect(
        getOwnerRootRedirectPath("/performance", "", owners, undefined, "?group=all"),
      ).toBeNull();
    });

    it("still redirects a bare /performance with no group query", () => {
      expect(getOwnerRootRedirectPath("/performance", "", owners, undefined, "")).toBe(
        "/performance/alice",
      );
    });

    it("does not treat an unrelated query param as group scope", () => {
      expect(
        getOwnerRootRedirectPath("/performance", "", owners, undefined, "?owner=alice"),
      ).toBe("/performance/alice");
    });

    it("leaves /portfolio root redirects unaffected by a group query", () => {
      expect(
        getOwnerRootRedirectPath("/portfolio", "", owners, undefined, "?group=all"),
      ).toBe("/portfolio/alice");
    });
  });

  describe("performance root defaults to the group view (#7214)", () => {
    const groups = [
      { slug: "all", name: "At a glance", members: ["alice"] },
      { slug: "adults", name: "Adults", members: ["alice"] },
    ];

    it("redirects a bare /performance to ?group=all when groups exist", () => {
      expect(getOwnerRootRedirectPath("/performance", "", owners, undefined, "", groups)).toBe(
        "/performance?group=all",
      );
    });

    it("carries the Dashboard's selected group when it is one of the groups", () => {
      expect(
        getOwnerRootRedirectPath("/performance", "", owners, undefined, "", groups, "adults"),
      ).toBe("/performance?group=adults");
    });

    it("ignores a preferred group that is not in the list", () => {
      expect(
        getOwnerRootRedirectPath("/performance", "", owners, undefined, "", groups, "nope"),
      ).toBe("/performance?group=all");
    });

    it("uses the first group when there is no 'all' group", () => {
      expect(
        getPerformanceRootRedirectPath(owners, [groups[1]], undefined, null),
      ).toBe("/performance?group=adults");
    });

    it("waits while groups are still loading", () => {
      expect(getOwnerRootRedirectPath("/performance", "", owners, undefined, "", null)).toBeNull();
    });

    it("falls back to the signed-in user's owner when there are no groups", () => {
      const multiOwners = [
        { owner: "alice", accounts: [], email: "alice@example.com" },
        { owner: "bob", accounts: [], email: "bob@example.com" },
      ];
      expect(
        getPerformanceRootRedirectPath(multiOwners, [], { email: "bob@example.com" }),
      ).toBe("/performance/bob");
    });

    it("leaves /portfolio root unaffected by groups", () => {
      expect(getOwnerRootRedirectPath("/portfolio", "", owners, undefined, "", groups)).toBe(
        "/portfolio/alice",
      );
    });
  });

  describe("with a logged-in user", () => {
    const multiOwners = [
      { owner: "alice", accounts: [], email: "alice@example.com" },
      { owner: "bob", accounts: [], email: "bob@example.com" },
    ];

    it("redirects to the owner matching the logged-in user's email", () => {
      expect(
        getOwnerRootRedirectPath("/portfolio", "", multiOwners, {
          email: "bob@example.com",
        })
      ).toBe("/portfolio/bob");
    });

    it("matches email case-insensitively", () => {
      expect(
        getOwnerRootRedirectPath("/portfolio", "", multiOwners, {
          email: "BOB@EXAMPLE.COM",
        })
      ).toBe("/portfolio/bob");
    });

    it("falls back to the first owner when the user has no matching owner", () => {
      expect(
        getOwnerRootRedirectPath("/portfolio", "", multiOwners, {
          email: "nobody@example.com",
        })
      ).toBe("/portfolio/alice");
    });

    it("falls back to the first owner when there is no logged-in user", () => {
      expect(getOwnerRootRedirectPath("/portfolio", "", multiOwners, null)).toBe(
        "/portfolio/alice"
      );
    });
  });
});
