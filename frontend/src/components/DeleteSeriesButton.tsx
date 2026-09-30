import { useEffect, useState } from "react";
import { deleteTimeseries, getSeriesReferences } from "../api";

type DeleteSeriesButtonProps = {
  ticker: string;
  exchange: string;
  onDeleted?: () => void;
};

/**
 * "Delete Series" action for the Research page (#8449). Rendered only when the
 * backend preflight reports the cached series is orphaned (no holdings,
 * transactions or instrument metadata) and the caller may delete it.
 */
export function DeleteSeriesButton({ ticker, exchange, onDeleted }: DeleteSeriesButtonProps) {
  const [canDelete, setCanDelete] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ kind: "success" | "error"; text: string } | null>(null);
  const label = `${ticker}.${exchange}`;

  useEffect(() => {
    let cancelled = false;
    setCanDelete(false);
    setMessage(null);
    if (!ticker || !exchange) return undefined;
    getSeriesReferences(ticker, exchange)
      .then((result) => {
        if (!cancelled) setCanDelete(result.can_delete);
      })
      .catch(() => {
        // Preflight failure just hides the action; the Research page is unaffected.
        if (!cancelled) setCanDelete(false);
      });
    return () => {
      cancelled = true;
    };
  }, [ticker, exchange]);

  async function handleDelete() {
    if (
      !window.confirm(
        `Delete the cached price series ${label}? This removes its stored prices and cannot be undone.`,
      )
    ) {
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      await deleteTimeseries(ticker, exchange);
      setCanDelete(false);
      setMessage({ kind: "success", text: `Deleted series ${label}.` });
      onDeleted?.();
    } catch (e) {
      setMessage({ kind: "error", text: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy(false);
    }
  }

  if (!canDelete && !message) return null;
  return (
    <>
      {canDelete && (
        <button type="button" onClick={handleDelete} disabled={busy} style={{ marginLeft: "1rem" }}>
          {busy ? "Deleting…" : "Delete Series"}
        </button>
      )}
      {message && (
        <span role={message.kind === "error" ? "alert" : "status"} style={{ marginLeft: "1rem" }}>
          {message.text}
        </span>
      )}
    </>
  );
}

export default DeleteSeriesButton;
