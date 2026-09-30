import { describe, expect, it } from "vitest";
import { ALL_PORTFOLIOS_SLUG } from "@/constants/portfolios";
import { DEFAULT_GROUP_SLUG } from "@/utils/groups";

describe("portfolio slug constants", () => {
  it("keeps the all-portfolios slug at the API contract value", () => {
    expect(ALL_PORTFOLIOS_SLUG).toBe("all");
  });

  it("uses the shared slug as the default group slug", () => {
    expect(DEFAULT_GROUP_SLUG).toBe(ALL_PORTFOLIOS_SLUG);
  });
});
