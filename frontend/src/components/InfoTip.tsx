import { useEffect, useId, useRef, useState, type MouseEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useInRouterContext } from 'react-router-dom';
import styles from './InfoTip.module.css';

interface InfoTipProps {
  /** Announced by assistive tech for the button itself, e.g. "What does RSI mean?". */
  label: string;
  /** The plain-English explanation shown in the popover. */
  children: string;
  /**
   * Optional path to a fuller explanation, e.g. "/metrics-explained#max-drawdown".
   * Rendered as a "Learn more" link inside the popover, via react-router's
   * Link when a Router is present (avoids a full page reload) and a plain
   * anchor otherwise (e.g. component tests rendered without a Router).
   */
  to?: string;
}

/**
 * A small "what does this mean?" affordance for jargon-heavy labels across
 * the app (see #7006 for its original home in the Plot HUD, #7230 for its
 * reuse on Performance/Trading/Screener). One icon, one sentence, discoverable
 * on hover for a mouse and on click/tap (which also covers keyboard
 * activation via a real `<button>`) for everyone else. This is the app's only
 * tooltip pattern — reuse it rather than adding another.
 */
export default function InfoTip({ label, children, to }: InfoTipProps) {
  const [open, setOpen] = useState(false);
  const popoverId = useId();
  const rootRef = useRef<HTMLSpanElement>(null);
  const { t } = useTranslation();
  const inRouterContext = useInRouterContext();

  useEffect(() => {
    if (!open) return undefined;

    function handlePointerDown(event: globalThis.MouseEvent) {
      if (
        rootRef.current &&
        !rootRef.current.contains(event.target as Node)
      ) {
        setOpen(false);
      }
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') setOpen(false);
    }

    document.addEventListener('mousedown', handlePointerDown);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('mousedown', handlePointerDown);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [open]);

  return (
    <span className={styles.infoTip} ref={rootRef}>
      <button
        type="button"
        className={styles.infoTipButton}
        aria-expanded={open}
        aria-controls={popoverId}
        aria-label={label}
        onClick={(event: MouseEvent<HTMLButtonElement>) => {
          // Info tips are frequently nested inside clickable rows/headers
          // (e.g. a sortable table header); stop the click reaching them.
          event.stopPropagation();
          setOpen((current) => !current);
        }}
      >
        <span aria-hidden="true">i</span>
      </button>
      <span
        role="tooltip"
        id={popoverId}
        className={`${styles.infoTipPopover} ${
          open ? styles.infoTipPopoverOpen : ''
        }`}
      >
        {children}
        {to && inRouterContext && (
          <Link
            to={to}
            className={styles.infoTipLink}
            onClick={(event: MouseEvent<HTMLAnchorElement>) =>
              event.stopPropagation()
            }
          >
            {t('common.learnMore', 'Learn more')}
          </Link>
        )}
        {to && !inRouterContext && (
          <a
            href={to}
            className={styles.infoTipLink}
            onClick={(event: MouseEvent<HTMLAnchorElement>) =>
              event.stopPropagation()
            }
          >
            {t('common.learnMore', 'Learn more')}
          </a>
        )}
      </span>
    </span>
  );
}
