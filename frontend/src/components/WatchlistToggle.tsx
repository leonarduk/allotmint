import { useEffect, useId, useRef, useState, type MouseEvent } from "react";
import { useTranslation } from "react-i18next";
import {
  createWatchlist,
  toggleInWatchlist,
  useWatchlists,
} from "../lib/watchlistStore";

interface Props {
  ticker: string;
  /** "star" for table rows; "button" for a labelled button (instrument page). */
  variant?: "star" | "button";
}

/**
 * Opens a picker listing every watchlist with a checkbox, so the user chooses
 * which list(s) a ticker goes on, plus "New watchlist…" to create one with
 * the ticker already in it. Filled star = on at least one list.
 */
export default function WatchlistToggle({ ticker, variant = "star" }: Props) {
  const { t } = useTranslation();
  const { lists, listsWith } = useWatchlists();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLSpanElement>(null);
  const menuId = useId();
  const memberOf = listsWith(ticker);
  const watched = memberOf.length > 0;

  useEffect(() => {
    if (!open) return;
    const onDocMouseDown = (e: globalThis.MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDocMouseDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDocMouseDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const label = t("watchlist.pickerLabel", { symbol: ticker });

  const onTriggerClick = (e: MouseEvent<HTMLButtonElement>) => {
    // Screen rows open the instrument detail on click; don't do that too.
    e.stopPropagation();
    setOpen((o) => !o);
  };

  const onCreate = () => {
    const name = window.prompt(t("watchlist.promptNew"))?.trim();
    if (!name) return;
    if (!createWatchlist(name, [ticker])) {
      window.alert(t("watchlist.nameTaken", { name }));
    }
  };

  const triggerText =
    variant === "star"
      ? watched
        ? "★"
        : "☆"
      : watched
        ? t("watchlist.onLists", { count: memberOf.length })
        : t("watchlist.addToWatchlist");

  return (
    <span
      ref={rootRef}
      className="relative inline-block"
      // Keep clicks/keys inside the picker from reaching a clickable row.
      onClick={(e) => e.stopPropagation()}
      onKeyDown={(e) => e.stopPropagation()}
    >
      <button
        type="button"
        onClick={onTriggerClick}
        aria-haspopup="true"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        aria-pressed={watched}
        aria-label={variant === "star" ? label : undefined}
        title={label}
        className={
          variant === "star"
            ? "ml-1 rounded border-0 bg-transparent p-0 align-middle text-lg leading-none text-amber-500"
            : undefined
        }
      >
        {triggerText}
      </button>
      {open && (
        <div
          id={menuId}
          role="group"
          aria-label={label}
          className="absolute left-0 z-20 mt-1 min-w-48 rounded border bg-white p-2 text-left text-sm shadow-lg dark:bg-gray-800"
        >
          {lists.map((l) => (
            <label
              key={l.id}
              className="flex cursor-pointer items-center gap-2 whitespace-nowrap py-0.5"
            >
              <input
                type="checkbox"
                checked={memberOf.some((m) => m.id === l.id)}
                onChange={() => toggleInWatchlist(l.id, ticker)}
              />
              {l.name}
            </label>
          ))}
          <button type="button" className="mt-1" onClick={onCreate}>
            {t("watchlist.newWithTicker")}
          </button>
        </div>
      )}
    </span>
  );
}
