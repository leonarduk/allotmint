import { describe, it, expect } from "vitest";
import { formatPublishedAt } from "@/lib/date";

const NOW = new Date("2024-06-10T12:00:00Z");

describe("formatPublishedAt", () => {
  it("returns null for missing or unparseable values", () => {
    expect(formatPublishedAt(null, NOW)).toBeNull();
    expect(formatPublishedAt(undefined, NOW)).toBeNull();
    expect(formatPublishedAt("", NOW)).toBeNull();
    expect(formatPublishedAt("not-a-date", NOW)).toBeNull();
  });

  it("formats recent timestamps as a relative age", () => {
    expect(formatPublishedAt("2024-06-07T12:00:00Z", NOW)).toBe("3 days ago");
    expect(formatPublishedAt("2024-06-10T10:00:00Z", NOW)).toBe("2 hours ago");
  });

  it("formats older timestamps in coarser units", () => {
    expect(formatPublishedAt("2024-03-10T12:00:00Z", NOW)).toBe("3 months ago");
    expect(formatPublishedAt("2022-06-10T12:00:00Z", NOW)).toBe("2 years ago");
  });
});
