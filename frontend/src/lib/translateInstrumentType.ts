import type { TFunction } from "i18next";

const MAP: Record<string, string> = {
  equity: "instrumentType.equity",
  bond: "instrumentType.bond",
  cash: "instrumentType.cash",
  fund: "instrumentType.fund",
  other: "instrumentType.other",
};

export const translateInstrumentType = (
  type: string | null | undefined,
  t: TFunction,
): string => {
  if (!type) return "—";
  const lower = type.toLowerCase();
  const key = MAP[lower];
  if (key) return t(key);
  const normalized = lower.replace(/_/g, " ");
  return normalized.charAt(0).toUpperCase() + normalized.slice(1);
};
