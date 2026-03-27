import { describe, expect, it } from "vitest";
import { getOwnerRootRedirectPath } from "@/App";

describe("getOwnerRootRedirectPath", () => {
  const owners = [{ owner: "alice", accounts: [] }];

  it("redirects portfolio root to first owner", () => {
    expect(getOwnerRootRedirectPath("/portfolio", "", owners)).toBe("/portfolio/alice");
  });

  it("redirects performance root to first owner", () => {
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
});
