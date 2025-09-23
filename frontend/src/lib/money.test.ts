import { describe, expect, it, vi } from "vitest";
import { money, percentOrNa } from "./money";

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

  it("warns and returns N/A for values outside -1..1", () => {
    const spy = vi.spyOn(console, "warn").mockImplementation(() => {});
    expect(percentOrNa(2)).toBe("N/A");
    expect(spy).toHaveBeenCalledWith("Metric value out of range:", 2);
    spy.mockRestore();
  });

  it("formats valid percentages", () => {
    expect(percentOrNa(0.123)).toBe("12.30%");
  });
});
