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
  it("accepts null config values for optional backend fields", () => {
    const parsed = configContractSchema.parse({
      app_env: "local",
      theme: null,
      tabs: {},
      relative_view_enabled: null,
      google_auth_enabled: false,
      google_client_id: null,
      disable_auth: true,
      allowed_emails: null,
      local_login_email: null,
  it("accepts null for optional backend-managed config fields", () => {
    const parsed = configContractSchema.parse({
      ...configFixture,
      theme: null,
      relative_view_enabled: null,
      allowed_emails: null,
    });

    expect(parsed.theme).toBeNull();
    expect(parsed.relative_view_enabled).toBeNull();
    expect(parsed.allowed_emails).toBeNull();
  });

  it("accepts configured non-null config values", () => {
    const parsed = configContractSchema.parse({
      app_env: "local",
      theme: "system",
      tabs: { group: true },
      relative_view_enabled: true,
      google_auth_enabled: true,
      google_client_id: "client-id-123",
      disable_auth: false,
      allowed_emails: ["user@example.com"],
      local_login_email: "user@example.com",
    });

    expect(parsed.theme).toBe("system");
    expect(parsed.relative_view_enabled).toBe(true);
    expect(parsed.allowed_emails).toEqual(["user@example.com"]);
  });

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

  it("validates a group portfolio response shape", () => {
    const groupFixture = {
      group: "children",
      slug: "children",
      name: "Children",
      members: ["alex", "joe"],
      as_of: "2026-03-23",
      total_value_estimate_gbp: 1234.56,
      accounts: [
        {
          account_type: "ISA",
          currency: "GBP",
          value_estimate_gbp: 1234.56,
          holdings: [],
        },
      ],
      members_summary: [
        {
          owner: "alex",
          total_value_estimate_gbp: 700,
          total_value_estimate_currency: "GBP",
          trades_this_month: 1,
          trades_remaining: 9,
        },
        {
          owner: "joe",
          total_value_estimate_gbp: 534.56,
          total_value_estimate_currency: "GBP",
          trades_this_month: 0,
          trades_remaining: 10,
        },
      ],
      subtotals_by_account_type: {
        ISA: 1234.56,
      },
    };
    expect(() => groupPortfolioContractSchema.parse(groupFixture)).not.toThrow();
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
      properties: expect.objectContaining({
        theme: expect.objectContaining({
          anyOf: expect.arrayContaining([
            expect.objectContaining({ type: "string" }),
            expect.objectContaining({ type: "null" }),
          ]),
        }),
      }),
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
