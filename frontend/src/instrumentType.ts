import type { TFunction } from "i18next";

/**
 * Format instrument type string into a human readable label.
 * Uses the provided translation function and falls back to a simple
 * capitalization when a translation key is missing.
 */
export function formatInstrumentType(
  t: TFunction,
  type?: string | null,
): string {
  if (!type) return t("common.other");
  const normalized = type.toLowerCase().replace(/_/g, " ");
  return normalized.charAt(0).toUpperCase() + normalized.slice(1);
}
