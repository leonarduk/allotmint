import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { API_CONTRACT_VERSION, apiContractJsonSchemas } from "@/contracts/apiContracts";

// Mirrors the payload shape written by frontend/scripts/generate-api-contract-schemas.mjs.
// Keep this endpoint list in sync with that script.
function buildExpectedBundle() {
  return {
    version: API_CONTRACT_VERSION,
    endpoints: {
      config: { path: "/config", schema: apiContractJsonSchemas.config },
      owners: { path: "/owners", schema: apiContractJsonSchemas.owners },
      groups: { path: "/groups", schema: apiContractJsonSchemas.groups },
      groupPortfolio: { path: "/portfolio-group/all", schema: apiContractJsonSchemas.groupPortfolio },
      portfolio: { path: "/portfolio/alice", schema: apiContractJsonSchemas.portfolio },
      transactions: { path: "/transactions", schema: apiContractJsonSchemas.transactions },
    },
  };
}

const generatedSchemaPath = path.resolve(
  process.cwd(),
  "src/contracts/generated/api-contract-schemas.v1.json",
);

describe("generated API contract schema bundle", () => {
  it("matches what generate-api-contract-schemas.mjs would produce from apiContracts.ts", () => {
    const committed = JSON.parse(readFileSync(generatedSchemaPath, "utf8"));
    const expected = buildExpectedBundle();

    // Structural comparison (not byte-for-byte) so trailing-newline/formatting
    // differences don't mask a real schema drift, and vice versa.
    expect(committed).toEqual(expected);
  });
});
