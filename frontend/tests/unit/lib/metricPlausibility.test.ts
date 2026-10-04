import { describe, it, expect } from "vitest";
import {
  classifyDrawdown,
  classifyMetric,
  drawdownNeedsAttention,
  DRAWDOWN_RANGE,
  RETURN_RANGE,
  TRACKING_ERROR_RANGE,
} from "@/lib/metricPlausibility";

// #8570: metrics are fractions; out-of-range values are "unreliable", never
// rescaled, and non-finite values are "missing".
describe("classifyMetric", () => {
  it.each([
    [0.0596, RETURN_RANGE, "ok"],
    [1.5, RETURN_RANGE, "ok"],
    [10, RETURN_RANGE, "ok"],
    [14159.17, RETURN_RANGE, "unreliable"],
    [-10.01, RETURN_RANGE, "unreliable"],
    [0.045, TRACKING_ERROR_RANGE, "ok"],
    [-0.01, TRACKING_ERROR_RANGE, "unreliable"],
    [2.5, TRACKING_ERROR_RANGE, "unreliable"],
    [-0.35, DRAWDOWN_RANGE, "ok"],
    [0.05, DRAWDOWN_RANGE, "unreliable"],
    [-1.5, DRAWDOWN_RANGE, "unreliable"],
    [null, RETURN_RANGE, "missing"],
    [undefined, RETURN_RANGE, "missing"],
    [Number.NaN, RETURN_RANGE, "missing"],
    [Number.POSITIVE_INFINITY, RETURN_RANGE, "missing"],
  ] as const)("classifies %s as %s", (value, range, expected) => {
    expect(classifyMetric(value, range)).toBe(expected);
  });
});

describe("classifyDrawdown", () => {
  it.each([
    [-0.35, "ok", false],
    [-0.9, "severe", true],
    [-0.95, "severe", true],
    [-1, "severe", true],
    [-1.5, "unreliable", true],
    [0.05, "unreliable", true],
    [null, "missing", false],
    [Number.NaN, "missing", false],
  ] as const)("classifies %s as %s", (value, state, attention) => {
    expect(classifyDrawdown(value)).toBe(state);
    expect(drawdownNeedsAttention(classifyDrawdown(value))).toBe(attention);
  });
});
