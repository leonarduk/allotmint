export const EXCHANGES = [
  "L",
  "N",
  "DE",
  "TO",
  "F",
  "CA",
] as const;
export type ExchangeCode = typeof EXCHANGES[number];
