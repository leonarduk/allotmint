import type { MouseEvent } from "react";
import { useTranslation } from "react-i18next";
import { useWatchlist } from "../lib/watchlistStore";

/** Star button that adds a ticker to, or removes it from, the watchlist. */
export default function WatchlistToggle({ ticker }: { ticker: string }) {
  const { t } = useTranslation();
  const { has, toggle } = useWatchlist();
  const watched = has(ticker);
  const label = watched
    ? t("watchlist.removeTicker", { symbol: ticker })
    : t("watchlist.addTicker", { symbol: ticker });

  const onClick = (e: MouseEvent<HTMLButtonElement>) => {
    // Screen rows open the instrument detail on click; don't do that too.
    e.stopPropagation();
    toggle(ticker);
  };

  return (
    <button
      type="button"
      onClick={onClick}
      onKeyDown={(e) => e.stopPropagation()}
      aria-pressed={watched}
      aria-label={label}
      title={label}
      className="ml-1 rounded border-0 bg-transparent p-0 align-middle text-lg leading-none text-amber-500"
    >
      {watched ? "★" : "☆"}
    </button>
  );
}
