import { describe, expect, it, vi } from "vitest";
import { money, percentOrNa } from "@/lib/money";

describe("money", () => {
  it("formats GBX values using pound units", () => {
    const value = 123.45;
    expect(money(value, "GBX", "en-GB")).toBe(
      money(value, "GBP", "en-GB"),
    );
  });
});

describe("percentOrNa", () => {
  it("returns N/A without warning for null or undefined", () => {
    const spy = vi.spyOn(console, "warn").mockImplementation(() => {});
    expect(percentOrNa(null)).toBe("N/A");
    expect(percentOrNa(undefined)).toBe("N/A");
    expect(spy).not.toHaveBeenCalled();
    spy.mockRestore();
  });

  it("warns and returns N/A for absurd values", () => {
    const spy = vi.spyOn(console, "warn").mockImplementation(() => {});
    expect(percentOrNa(1200)).toBe("N/A");
    expect(spy).toHaveBeenCalledWith("Metric value out of range:", 1200);
    spy.mockRestore();
  });

  it("formats fractional percentages", () => {
    expect(percentOrNa(0.123)).toBe("12.30%");
  });

  it("normalises whole percentages", () => {
    expect(percentOrNa(3.44)).toBe("3.44%");
  });
});
