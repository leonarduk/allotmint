export const FX_CURRENCIES = ["USD", "EUR", "CHF", "JPY", "CAD"] as const;
export type FxCurrency = (typeof FX_CURRENCIES)[number];

export const isSupportedFx = (ccy?: string | null): ccy is FxCurrency =>
  ccy != null && FX_CURRENCIES.includes(ccy as FxCurrency);

export const fxTicker = (ccy: FxCurrency): string => `${ccy}GBP=X`;
