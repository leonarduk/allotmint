import styles from '../plot.module.css';

export type MeterTone = 'growth' | 'water' | 'sun' | 'feed';

const TONE_CLASS: Record<MeterTone, string> = {
  growth: '',
  water: styles.meterFillWater,
  sun: styles.meterFillSun,
  feed: styles.meterFillFeed,
};

interface MeterProps {
  /** 0–100. */
  pct: number;
  tone?: MeterTone;
  /** Announced by screen readers in place of the bare percentage. */
  label: string;
}

/**
 * A HUD bar. Rendered as a real progressbar so the game chrome stays
 * navigable with assistive tech rather than being decorative pixels.
 */
export default function Meter({ pct, tone = 'growth', label }: MeterProps) {
  const clamped = Math.max(0, Math.min(100, Number.isFinite(pct) ? pct : 0));
  return (
    <div
      className={styles.meter}
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(clamped)}
      aria-valuetext={label}
      aria-label={label}
    >
      <div
        className={`${styles.meterFill} ${TONE_CLASS[tone]}`}
        style={{ width: `${clamped}%` }}
      />
    </div>
  );
}
