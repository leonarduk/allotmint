import type { CSSProperties } from 'react';
import styles from '../plot.module.css';

interface RadialProgressProps {
  /** 0–100. */
  pct: number;
  value: string;
  label: string;
  caption?: string;
}

/**
 * The big completion ring on the chores screen — a conic-gradient donut with
 * the headline figure in the middle.
 */
export default function RadialProgress({
  pct,
  value,
  label,
  caption,
}: RadialProgressProps) {
  const clamped = Math.max(0, Math.min(100, Number.isFinite(pct) ? pct : 0));
  const ringStyle = { '--plot-ring-pct': clamped } as CSSProperties;
  return (
    <div className={styles.radialWrap}>
      <div
        className={styles.radial}
        style={ringStyle}
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(clamped)}
        aria-valuetext={`${label}: ${value}`}
        aria-label={label}
      >
        <div className={styles.radialInner}>
          <div>
            <div className={styles.radialValue}>{value}</div>
            <div className={styles.radialLabel}>{label}</div>
          </div>
        </div>
      </div>
      {caption && <div className={styles.radialCaption}>{caption}</div>}
    </div>
  );
}
