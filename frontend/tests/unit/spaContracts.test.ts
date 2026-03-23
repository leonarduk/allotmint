import { describe, expect, it } from "vitest";

import fixture from "../fixtures/spaContracts.json";
import {
  SPA_RESPONSE_CONTRACT_VERSION,
  configContractSchema,
  groupSummaryContractSchema,
  ownerSummaryContractSchema,
  portfolioContractSchema,
  spaContractEnvelopeSchema,
  transactionContractSchema,
} from "@/contracts/spa";

describe("SPA response contracts", () => {
  it("validates the shared contract fixture envelope", () => {
    const parsed = spaContractEnvelopeSchema.parse(fixture);
    expect(parsed.version).toBe(SPA_RESPONSE_CONTRACT_VERSION);
  });

  it("pins each high-value endpoint fixture separately", () => {
    expect(() => configContractSchema.parse(fixture.config)).not.toThrow();
    expect(() =>
      ownerSummaryContractSchema.array().parse(fixture.owners),
    ).not.toThrow();
    expect(() =>
      groupSummaryContractSchema.array().parse(fixture.groups),
    ).not.toThrow();
    expect(() => portfolioContractSchema.parse(fixture.portfolio)).not.toThrow();
    expect(() =>
      transactionContractSchema.array().parse(fixture.transactions),
    ).not.toThrow();
  });
});
