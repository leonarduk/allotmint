export const FX_CURRENCIES = ["USD", "EUR"] as const;
export type FxCurrency = typeof FX_CURRENCIES[number];

export const isSupportedFx = (ccy?: string | null): ccy is FxCurrency =>
  ccy != null && (FX_CURRENCIES as readonly string[]).includes(ccy);

export const fxTicker = (ccy: FxCurrency): string => `GBP${ccy}=X`;
