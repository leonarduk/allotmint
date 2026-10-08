import { describe, expect, it } from "vitest";
import i18n from "@/i18n";
import { instrumentTooltip } from "@/lib/instrumentType";

describe("instrumentTooltip", () => {
  const t = i18n.t.bind(i18n);

  it("combines the full name with the translated instrument type", () => {
    expect(instrumentTooltip(t, "REC.L", "Recordati Industria Chimica", "equity")).toBe(
      "Recordati Industria Chimica · Equity",
    );
  });

  it("falls back to the ticker when the name is missing or blank", () => {
    expect(instrumentTooltip(t, "REC.L", null, "Investment Trust")).toBe(
      "REC.L · Investment Trust",
    );
    expect(instrumentTooltip(t, "REC.L", "  ", "etf")).toBe("REC.L · ETF");
  });

  it("omits the type when it is unknown rather than showing Other", () => {
    expect(instrumentTooltip(t, "REC.L", "Recordati", null)).toBe("Recordati");
    expect(instrumentTooltip(t, "REC.L", "Recordati", " ")).toBe("Recordati");
  });
});
