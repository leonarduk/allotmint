import type {TFunction} from "i18next";

const TYPE_KEYS: Record<string, string> = {
  equity: "instrumentType.equity",
  bond: "instrumentType.bond",
  cash: "instrumentType.cash",
  etf: "instrumentType.etf",
  fund: "instrumentType.fund",
  "investment trust": "instrumentType.investmentTrust",
  "real estate": "instrumentType.realEstate",
};

export function translateInstrumentType(t: TFunction, type?: string | null) {
  if (!type) {
    return t("instrumentType.other", {defaultValue: t("common.other")});
  }
  const key = TYPE_KEYS[type.toLowerCase()];
  return t(key || "instrumentType.other", {defaultValue: type});
}
