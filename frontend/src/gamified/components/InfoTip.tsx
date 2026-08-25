import { useEffect, useId, useRef, useState } from 'react';
import styles from '../plot.module.css';

interface InfoTipProps {
  /** Announced by assistive tech for the button itself, e.g. "What does Water mean?". */
  label: string;
  /** The plain-English explanation shown in the popover. */
  children: string;
}

/**
 * A small "what does this mean?" affordance for jargon-heavy HUD chrome
 * (WATER/FEED/SUNLIGHT, growth stages, season tiers) — see #7006. Deliberately
 * not a full onboarding tour: one icon, one sentence, discoverable on hover
 * for a mouse and on click/tap (which also covers keyboard activation via a
 * real `<button>`) for everyone else.
 */
export default function InfoTip({ label, children }: InfoTipProps) {
  const [open, setOpen] = useState(false);
  const popoverId = useId();
  const rootRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!open) return undefined;

    function handlePointerDown(event: MouseEvent) {
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
        onClick={() => setOpen((current) => !current)}
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
      </span>
    </span>
  );
}
