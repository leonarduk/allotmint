import { useEffect, useState } from "react";
import { resolveMorningstarId } from "../api";

/**
 * The instrument's Morningstar SecId: the saved one from the catalogue, or
 * one the backend looks up (by ISIN and listing) and saves on first view.
 * Null while unknown, so callers can fall back to a Morningstar search.
 */
export function useMorningstarId(
  ticker: string,
  exchange: string | null | undefined,
  isin: string | null | undefined,
  savedId: string | null | undefined,
): string | null {
  const key = `${exchange ?? ""}/${ticker}/${isin ?? ""}`;
  const [resolved, setResolved] = useState<{ key: string; id: string | null } | null>(null);

  useEffect(() => {
    if (savedId || !isin || !ticker || !exchange) return;
    let cancelled = false;
    resolveMorningstarId(ticker, exchange)
      .then((res) => {
        if (!cancelled) setResolved({ key, id: res.morningstar_id ?? null });
      })
      .catch((err) => {
        if (!cancelled) console.warn("Could not resolve Morningstar id:", err);
      });
    return () => {
      cancelled = true;
    };
  }, [key, ticker, exchange, isin, savedId]);

  if (savedId) return savedId;
  return resolved?.key === key ? resolved.id : null;
}
