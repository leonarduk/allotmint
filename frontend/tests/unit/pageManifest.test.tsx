import { describe, expect, it } from "vitest";
import { MODES } from "@/modes";
import {
  buildPathForMode,
  deriveModeFromPathname,
  getMenuEntries,
  MENU_CATEGORY_ORDER,
  PAGE_MANIFEST,
  validatePageManifest,
} from "@/pageManifest";

describe("pageManifest", () => {
  it("keeps route metadata unique and covers every mode", () => {
    const validation = validatePageManifest();

    expect(validation.duplicateModes).toEqual([]);
    expect(validation.duplicateSegments).toEqual([]);
    expect(PAGE_MANIFEST.map((entry) => entry.mode).sort()).toEqual([...MODES].sort());
  });

  it("keeps menu metadata aligned with configured menu sections", () => {
    for (const entry of PAGE_MANIFEST) {
      if (!entry.menu) continue;
      expect(MENU_CATEGORY_ORDER[entry.menu.section]).toContain(entry.menu.category);
      expect(getMenuEntries(entry.menu.section)).toContainEqual(entry);
    }
  });

  it("derives modes and paths from the same manifest", () => {
    expect(deriveModeFromPathname("/")).toBe("group");
    expect(deriveModeFromPathname("/portfolio/alex")).toBe("owner");
    expect(deriveModeFromPathname("/alerts")).toBe("alerts");
    expect(deriveModeFromPathname("/alert-settings")).toBe("alertsettings");
    expect(deriveModeFromPathname("/support")).toBe("support");
    expect(deriveModeFromPathname("/totally-unknown")).toBe("movers");

    expect(buildPathForMode("group", { group: "all" })).toBe("/");
    expect(buildPathForMode("group", { group: "kids" })).toBe("/?group=kids");
    expect(buildPathForMode("owner", { owner: "alex" })).toBe("/portfolio/alex");
    expect(buildPathForMode("pension")).toBe("/pension/forecast");
  });
});
