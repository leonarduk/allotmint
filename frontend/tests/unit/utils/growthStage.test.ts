import { describe, expect, it } from "vitest";
import { getGrowthStage } from "@/utils/growthStage";

describe("getGrowthStage", () => {
  it("returns the unknown stage when daysHeld is null (no acquisition date on record)", () => {
    const info = getGrowthStage({ daysHeld: null });
    expect(info.stage).toBe("unknown");
    expect(info.icon).not.toBe("🌱");
  });

  it("returns the unknown stage when daysHeld is undefined", () => {
    const info = getGrowthStage({});
    expect(info.stage).toBe("unknown");
  });

  it("does not report unknown as the same stage as a genuine new position", () => {
    const unknown = getGrowthStage({ daysHeld: null });
    const seed = getGrowthStage({ daysHeld: 5 });
    expect(unknown.stage).not.toBe(seed.stage);
  });

  it("still reports harvest when the price target is met even without a days-held value", () => {
    const info = getGrowthStage({
      daysHeld: null,
      currentPrice: 12,
      targetPrice: 10,
    });
    expect(info.stage).toBe("harvest");
  });

  it("classifies a genuine new position as seed", () => {
    expect(getGrowthStage({ daysHeld: 5 }).stage).toBe("seed");
  });

  it("classifies a mid-length hold as growing", () => {
    expect(getGrowthStage({ daysHeld: 45 }).stage).toBe("growing");
  });

  it("classifies a long-term hold as harvest", () => {
    expect(getGrowthStage({ daysHeld: 200 }).stage).toBe("harvest");
  });
});
