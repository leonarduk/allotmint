import { describe, expect, it } from "vitest";

import {
  buildTemplatePayload,
  slugifyTemplateId,
} from "@/components/ReportBuilder/sections";

// Mirrors backend/reports.py _TEMPLATE_ID_RE: the id is also a download URL segment.
const TEMPLATE_ID_RE = /^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$/;

describe("slugifyTemplateId", () => {
  it.each([
    ["QA temp template", "qa-temp-template"],
    ["  Café / ISA £ report!  ", "cafe-isa-report"],
    ["---", "custom-template"],
    ["a".repeat(80), "a".repeat(64)],
    [`${"a".repeat(63)} b`, "a".repeat(63)],
  ])("turns %j into a backend-valid id", (name, expected) => {
    const id = slugifyTemplateId(name);
    expect(id).toBe(expected);
    expect(id).toMatch(TEMPLATE_ID_RE);
  });
});

describe("buildTemplatePayload", () => {
  it("maps sections onto backend sources, keeping only the chosen columns", () => {
    const payload = buildTemplatePayload(
      {
        name: "Mixed",
        description: "Two sections",
        sections: [
          { id: "transactions", columns: ["date", "amount_gbp"] },
          { id: "risk", columns: ["metric", "value"] },
        ],
      },
      (option) => option.id.toUpperCase(),
    );

    expect(payload).toEqual({
      template_id: "mixed",
      name: "Mixed",
      description: "Two sections",
      sections: [
        {
          id: "transactions",
          title: "TRANSACTIONS",
          source: "transactions",
          columns: [
            { key: "date", label: "Date", type: "date" },
            { key: "amount_gbp", label: "Amount (GBP)", type: "number" },
          ],
        },
        {
          id: "risk",
          title: "RISK",
          source: "performance.risk",
          columns: [
            { key: "metric", label: "Metric", type: "string" },
            { key: "value", label: "Value", type: "number" },
          ],
        },
      ],
    });
  });

  it("rejects an unknown section rather than sending it", () => {
    expect(() =>
      buildTemplatePayload(
        { name: "Bad", sections: [{ id: "nope", columns: ["x"] }] },
        () => "",
      ),
    ).toThrow("Unknown report section 'nope'");
  });
});
