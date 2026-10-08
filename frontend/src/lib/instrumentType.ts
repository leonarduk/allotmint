import type { TFunction } from "i18next";

// Keys are lower-cased: instrument types and asset classes reach the UI in
// both legacy ("Equity", "Bond") and post-#9196 canonical ("equity", "bond")
// casing, and both must render the same label.
const TYPE_KEYS: Record<string, string> = {
  equity: "instrumentType.equity",
  bond: "instrumentType.bond",
  cash: "instrumentType.cash",
  commodity: "instrumentType.commodity",
  etf: "instrumentType.etf",
  fund: "instrumentType.fund",
  "investment trust": "instrumentType.investmentTrust",
  "multi-asset": "instrumentType.multiAsset",
  property: "instrumentType.realEstate",
  "real estate": "instrumentType.realEstate",
  other: "instrumentType.other",
};

export function translateInstrumentType(t: TFunction, type?: string | null) {
  if (!type) {
    return t("instrumentType.other", { defaultValue: t("common.other") });
  }
  const key = TYPE_KEYS[type.trim().toLowerCase()];
  return key ? t(key, { defaultValue: type }) : type;
}

/**
 * Hover text for an instrument's ticker/name cell: the full (untruncated)
 * name plus its translated instrument type, e.g. "Rentokil Initial · Equity".
 * The type is omitted when unknown rather than shown as a misleading "Other".
 */
export function instrumentTooltip(
  t: TFunction,
  ticker: string,
  name?: string | null,
  type?: string | null,
) {
  const label = name?.trim() || ticker;
  return type?.trim() ? `${label} · ${translateInstrumentType(t, type)}` : label;
}
