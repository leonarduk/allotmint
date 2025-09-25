import type { InstrumentSummary } from "../types";

export type InstrumentWithIdentity = Pick<
  InstrumentSummary,
  "instrument_type" | "ticker"
>;

export function isCashInstrument({
  instrument_type,
  ticker,
}: InstrumentWithIdentity): boolean {
  const type = instrument_type?.toLowerCase();
  if (type === "cash") {
    return true;
  }

  const symbol = ticker?.toUpperCase();
  return symbol?.startsWith("CASH") ?? false;
}
