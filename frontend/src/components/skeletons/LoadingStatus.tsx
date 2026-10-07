import { useEffect, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

/**
 * How long a load may run before we say it is still going. Cold backend calls
 * take 10-40s (#7215); past this point a pulsing skeleton alone reads as a hang
 * and invites a reload, which restarts the slow request.
 */
export const SLOW_LOAD_HINT_MS = 5000;

interface Props {
  label: string;
  children: ReactNode;
  className?: string;
  /**
   * Delay before the visible "still working" hint appears. Pass `null` when
   * another LoadingStatus on the same screen already carries the hint.
   */
  slowAfterMs?: number | null;
}

/**
 * Wraps a visual skeleton so screen readers still announce a loading state,
 * and tells everyone the load is still running once it passes `slowAfterMs`.
 */
export default function LoadingStatus({
  label,
  children,
  className,
  slowAfterMs = SLOW_LOAD_HINT_MS,
}: Props) {
  const { t } = useTranslation();
  const [slow, setSlow] = useState(false);

  useEffect(() => {
    if (slowAfterMs === null) return undefined;
    const timer = setTimeout(() => setSlow(true), slowAfterMs);
    return () => clearTimeout(timer);
  }, [slowAfterMs]);

  return (
    <div role="status" aria-live="polite" aria-label={label} className={className}>
      <span className="sr-only">{label}</span>
      {children}
      {slow && (
        <p className="mt-2 text-sm text-gray-400" data-testid="loading-still-working">
          {t("app.stillLoading")}
        </p>
      )}
    </div>
  );
}
