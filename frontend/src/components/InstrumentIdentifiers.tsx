import { useTranslation } from "react-i18next";
import type { InstrumentMetadata } from "../types";

type Props = {
  /** Full TICKER.EXCHANGE symbol shown for the instrument. */
  ticker: string;
  exchange: string | null | undefined;
  isin: string | null | undefined;
  /** Matching catalogue entry, when the instrument is in the catalogue. */
  entry: InstrumentMetadata | null;
};

const itemStyle = { marginBottom: "0.5rem" };

function text(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed && trimmed.toLowerCase() !== "none" ? trimmed : null;
}

function priceSourceSymbol(entry: InstrumentMetadata | null): string | null {
  const source = entry?.price_source;
  const ticker = text(source?.ticker);
  if (!ticker) return null;
  const exchange = text(source?.exchange);
  return exchange ? `${ticker}.${exchange}`.toUpperCase() : ticker.toUpperCase();
}

/**
 * Read-only identifier and classification rows for the "Instrument info"
 * list. Ticker, ISIN and exchange always render (with a dash when unknown)
 * so users can see what is missing; the optional catalogue classifications
 * only render when the catalogue has a value.
 */
export function InstrumentIdentifiers({ ticker, exchange, isin, entry }: Props) {
  const { t } = useTranslation();
  const optional: [string, string | null][] = [
    ["assetClass", text(entry?.asset_class)],
    ["region", text(entry?.region)],
    ["industry", text(entry?.industry)],
    ["grouping", text(entry?.grouping)],
    ["priceSource", priceSourceSymbol(entry)],
  ];
  return (
    <>
      <li style={itemStyle}>
        {t("instrumentDetail.identifiers.ticker")}: {ticker || "—"}
      </li>
      <li style={itemStyle}>
        {t("instrumentDetail.identifiers.isin")}: {text(isin) ?? "—"}
      </li>
      <li style={itemStyle}>
        {t("instrumentDetail.identifiers.exchange")}: {text(exchange)?.toUpperCase() ?? "—"}
      </li>
      {optional.map(([key, value]) =>
        value ? (
          <li key={key} style={itemStyle}>
            {t(`instrumentDetail.identifiers.${key}`)}: {value}
          </li>
        ) : null,
      )}
    </>
  );
}
