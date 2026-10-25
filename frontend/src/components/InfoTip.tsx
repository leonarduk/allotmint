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

type Placement = 'above' | 'below';

/** Gap between trigger and popover; mirrors `0.45rem` in InfoTip.module.css. */
const POPOVER_GAP_PX = 8;
/**
 * Height assumed for a popover that is not laid out yet (it is
 * `display: none` while closed, so it measures 0). Roughly a three-line
 * explanation plus a "Learn more" link.
 */
const ESTIMATED_POPOVER_HEIGHT_PX = 120;

/**
 * Prefer showing the popover above the trigger, but flip it below when there
 * is not enough room above (e.g. an InfoTip in a table header at the top of
 * the viewport), so it is never clipped off-screen (#7364).
 */
function choosePlacement(
  trigger: HTMLElement,
  popover: HTMLElement | null
): Placement {
  const popoverHeight = popover?.offsetHeight || ESTIMATED_POPOVER_HEIGHT_PX;
  const spaceAbove = trigger.getBoundingClientRect().top;
  return spaceAbove >= popoverHeight + POPOVER_GAP_PX ? 'above' : 'below';
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
  const [placement, setPlacement] = useState<Placement>('above');
  const popoverId = useId();
  const rootRef = useRef<HTMLSpanElement>(null);
  const popoverRef = useRef<HTMLSpanElement>(null);
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

  // Re-measured on every way the popover can appear: hover and focus (both
  // shown via CSS) and click (shown via the `open` state).
  function updatePlacement() {
    if (!rootRef.current) return;
    setPlacement(choosePlacement(rootRef.current, popoverRef.current));
  }

  return (
    <span
      className={styles.infoTip}
      ref={rootRef}
      onMouseEnter={updatePlacement}
      onFocus={updatePlacement}
    >
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
          updatePlacement();
          setOpen((current) => !current);
        }}
      >
        {/* eslint-disable-next-line i18next/no-literal-string -- decorative icon, aria-hidden */}
        <span aria-hidden="true">i</span>
      </button>
      <span
        role="tooltip"
        id={popoverId}
        ref={popoverRef}
        data-placement={placement}
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
