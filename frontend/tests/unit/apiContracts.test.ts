import { describe, expect, it } from "vitest";
import configFixture from "@/contracts/fixtures/config.v1.json";
import groupsFixture from "@/contracts/fixtures/groups.v1.json";
import ownersFixture from "@/contracts/fixtures/owners.v1.json";
import portfolioFixture from "@/contracts/fixtures/portfolio.v1.json";
import transactionsFixture from "@/contracts/fixtures/transactions.v1.json";
import {
  apiContractJsonSchemas,
  configContractSchema,
  groupPortfolioContractSchema,
  groupsContractSchema,
  ownersContractSchema,
  portfolioContractSchema,
  transactionsContractSchema,
} from "@/contracts/apiContracts";

describe("API contract fixtures", () => {
  it("validates the config fixture", () => {
    expect(() => configContractSchema.parse(configFixture)).not.toThrow();
  });

  it("validates the owners fixture", () => {
    expect(() => ownersContractSchema.parse(ownersFixture)).not.toThrow();
  });

  it("validates the groups fixture", () => {
    expect(() => groupsContractSchema.parse(groupsFixture)).not.toThrow();
  });

  it("validates the portfolio fixture", () => {
    expect(() => portfolioContractSchema.parse(portfolioFixture)).not.toThrow();
  });

  it("validates the transactions fixture", () => {
    expect(() => transactionsContractSchema.parse(transactionsFixture)).not.toThrow();
  });

  it("accepts a group portfolio payload with slug", () => {
    const payload = {
      slug: "all",
      name: "At a glance",
      as_of: "2026-03-24",
      members: ["alice", "bob"],
      total_value_estimate_gbp: 1000,
      accounts: [],
      members_summary: [],
      subtotals_by_account_type: {},
    };

    expect(() => groupPortfolioContractSchema.parse(payload)).not.toThrow();
  });

  it("rejects legacy group portfolio payloads with group instead of slug", () => {
    const legacyPayload = {
      group: "all",
      name: "At a glance",
      as_of: "2026-03-24",
      members: ["alice", "bob"],
      total_value_estimate_gbp: 1000,
      accounts: [],
      members_summary: [],
      subtotals_by_account_type: {},
    };

    expect(() => groupPortfolioContractSchema.parse(legacyPayload)).toThrow();
  });

  it("exports machine-readable JSON Schema definitions", () => {
    expect(apiContractJsonSchemas.config).toMatchObject({
      type: "object",
      required: expect.arrayContaining(["app_env", "tabs", "theme"]),
    });
    expect(apiContractJsonSchemas.owners).toMatchObject({ type: "array" });
    expect(apiContractJsonSchemas.portfolio).toMatchObject({ type: "object" });
  });

  it("treats fixtures as examples instead of exact snapshots", () => {
    const owners = structuredClone(ownersFixture);
    owners[0] = {
      ...owners[0],
      email: null,
    };

    expect(() => ownersContractSchema.parse(owners)).not.toThrow();
    expect(owners).not.toEqual(ownersFixture);
  });
});
