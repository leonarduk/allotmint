import { describe, expect, it } from "vitest";
import configFixture from "@/contracts/fixtures/config.v1.json";
import groupsFixture from "@/contracts/fixtures/groups.v1.json";
import ownersFixture from "@/contracts/fixtures/owners.v1.json";
import portfolioFixture from "@/contracts/fixtures/portfolio.v1.json";
import transactionsFixture from "@/contracts/fixtures/transactions.v1.json";
import {
  apiContractJsonSchemas,
  configContractSchema,
  groupsContractSchema,
  ownersContractSchema,
  portfolioContractSchema,
  transactionsContractSchema,
} from "@/contracts/apiContracts";

describe("API contract fixtures", () => {
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
