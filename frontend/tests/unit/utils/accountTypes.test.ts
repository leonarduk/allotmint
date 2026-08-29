import { describe, expect, it } from "vitest";
import {
  accountTypeLabel,
  countsTowardPensionForecast,
} from "@/utils/accountTypes";

describe("accountTypeLabel", () => {
  it("renders known account_type slugs as their display label, not the raw slug", () => {
    expect(accountTypeLabel("isa")).toBe("ISA");
    expect(accountTypeLabel("sipp")).toBe("SIPP");
    expect(accountTypeLabel("gia")).toBe("GIA");
    expect(accountTypeLabel("jisa")).toBe("JISA");
    expect(accountTypeLabel("lisa")).toBe("LISA");
  });

  it("is case-insensitive and trims whitespace", () => {
    expect(accountTypeLabel("SIPP")).toBe("SIPP");
    expect(accountTypeLabel("  isa  ")).toBe("ISA");
  });

  // #7211 constraint: account-type handling must not assume ISA/SIPP are
  // the only two types -- an unknown slug should still fail safe to a
  // readable label rather than the raw lowercase string.
  it("falls back to a title-cased version of an unknown account_type slug", () => {
    expect(accountTypeLabel("brokerage")).toBe("Brokerage");
    expect(accountTypeLabel("workplace-sipp")).toBe("Workplace Sipp");
    expect(accountTypeLabel("joint_account")).toBe("Joint Account");
  });
});

describe("countsTowardPensionForecast", () => {
  // Mirrors backend/common/pension.py's DEFINED_CONTRIBUTION_ACCOUNT_MARKERS
  // + dc_pension_pot_gbp exactly: substring match on "sipp", not exact
  // equality. See tests/backend/common/test_pension.py's
  // test_dc_pension_pot_gbp_sums_sipp_accounts_only for the backend side of
  // this same contract.
  it("matches account_type by substring, like the backend", () => {
    expect(countsTowardPensionForecast("sipp")).toBe(true);
    expect(countsTowardPensionForecast("kz:sipp")).toBe(true);
    expect(countsTowardPensionForecast("workplace-sipp")).toBe(true);
  });

  it("is case-insensitive and trims whitespace", () => {
    expect(countsTowardPensionForecast("SIPP")).toBe(true);
    expect(countsTowardPensionForecast("  Sipp  ")).toBe(true);
  });

  // Regression case from #7211 follow-up review: an account_type of exactly
  // "pension" reads like a pension but is NOT one of the backend's markers,
  // so it must NOT be counted here either -- otherwise the frontend's seeded
  // pot would include a value the backend's own forecast run excludes.
  it("does not match 'pension' -- the backend only recognises 'sipp'-family markers", () => {
    expect(countsTowardPensionForecast("pension")).toBe(false);
  });

  it("does not match non-pension account types, including unknown ones", () => {
    expect(countsTowardPensionForecast("isa")).toBe(false);
    expect(countsTowardPensionForecast("gia")).toBe(false);
    expect(countsTowardPensionForecast("cash")).toBe(false);
    expect(countsTowardPensionForecast("savings")).toBe(false);
    // Unknown type: fails safe to "does not count" rather than accidentally
    // matching via `Set.has` type coercion or similar.
    expect(countsTowardPensionForecast("brokerage")).toBe(false);
  });
});
