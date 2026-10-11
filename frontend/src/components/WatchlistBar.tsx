import { useTranslation } from "react-i18next";
import {
  copyWatchlist,
  createWatchlist,
  deleteWatchlist,
  renameWatchlist,
  setActiveWatchlist,
  suggestCopyName,
  useWatchlists,
} from "../lib/watchlistStore";

/**
 * Pick, create, rename, copy and delete named watchlists. Uses
 * window.prompt/confirm like the Screen tab's saved-screens bar.
 */
export function WatchlistBar() {
  const { t } = useTranslation();
  const { state, lists, active } = useWatchlists();

  function promptName(message: string, initial = ""): string | null {
    const name = window.prompt(message, initial)?.trim();
    return name ? name : null;
  }

  function alertTaken(name: string) {
    window.alert(t("watchlist.nameTaken", { name }));
  }

  function handleNew() {
    const name = promptName(t("watchlist.promptNew"));
    if (name && !createWatchlist(name)) alertTaken(name);
  }

  function handleRename() {
    const name = promptName(t("watchlist.promptRename"), active.name);
    if (name && name !== active.name && !renameWatchlist(active.id, name)) {
      alertTaken(name);
    }
  }

  function handleCopy() {
    const name = promptName(
      t("watchlist.promptCopy"),
      suggestCopyName(state, active.name),
    );
    if (name && !copyWatchlist(active.id, name)) alertTaken(name);
  }

  function handleDelete() {
    if (window.confirm(t("watchlist.confirmDelete", { name: active.name }))) {
      deleteWatchlist(active.id);
    }
  }

  const label = t("watchlist.listLabel");
  return (
    <div className="mb-3 flex flex-wrap items-center gap-2">
      <label className="flex items-center gap-1">
        {label}
        <select
          aria-label={label}
          value={active.id}
          onChange={(e) => setActiveWatchlist(e.target.value)}
          className="border px-2 py-1"
        >
          {lists.map((l) => (
            <option key={l.id} value={l.id}>
              {t("watchlist.listOption", {
                name: l.name,
                count: l.symbols.length,
              })}
            </option>
          ))}
        </select>
      </label>
      <button type="button" onClick={handleNew}>
        {t("watchlist.newList")}
      </button>
      <button type="button" onClick={handleRename}>
        {t("watchlist.renameList")}
      </button>
      <button type="button" onClick={handleCopy}>
        {t("watchlist.copyList")}
      </button>
      <button
        type="button"
        onClick={handleDelete}
        disabled={lists.length < 2}
        title={lists.length < 2 ? t("watchlist.cannotDeleteLast") : undefined}
      >
        {t("watchlist.deleteList")}
      </button>
    </div>
  );
}

export default WatchlistBar;
