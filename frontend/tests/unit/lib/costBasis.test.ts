import { describe, expect, it } from "vitest";
import { isCostBasisEstimate, isCostBasisUnreliable } from "@/lib/costBasis";

// Pinned list; must match COST_BASIS_UNRELIABLE_SOURCES in
// backend/common/holding_utils.py, whose own test
// (tests/test_holding_utils_price_cost_basis.py::test_cost_basis_unreliable_sources_contents)
// pins the same set. Update both together.
const EXPECTED_UNRELIABLE = ["unknown", "book_suspect"];

describe("isCostBasisUnreliable", () => {
  it.each(EXPECTED_UNRELIABLE)("treats %s as unreliable", (source) => {
    expect(isCostBasisUnreliable(source)).toBe(true);
  });

  // "estimate" (#10095) is shown with its gain, but marked: see isCostBasisEstimate.
  it.each(["book", "derived", "estimate", "cash", "none", "", null, undefined])(
    "treats %s as reliable",
    (source) => {
      expect(isCostBasisUnreliable(source)).toBe(false);
    },
  );
});

describe("isCostBasisEstimate", () => {
  it("is true only for an estimated cost (#10095)", () => {
    expect(isCostBasisEstimate("estimate")).toBe(true);
    for (const source of ["book", "derived", "unknown", "book_suspect", null, undefined]) {
      expect(isCostBasisEstimate(source)).toBe(false);
    }
  });
});
