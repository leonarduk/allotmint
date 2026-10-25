import { useTranslation } from 'react-i18next';
import styles from '../plot.module.css';
import { clamp, formatShare } from '../plotModel';

/**
 * A thin bar filled in proportion to a crop's share of plot value. Purely
 * visual: callers always print the figure beside it, so it is hidden from
 * assistive tech rather than announced twice.
 */
export function ShareTrack({ share }: { share: number }) {
  return (
    <span className={styles.shareTrack} aria-hidden="true">
      <span
        className={styles.shareFill}
        style={{ width: `${clamp(share * 100, 0, 100)}%` }}
      />
    </span>
  );
}

/**
 * How much of the plot a crop takes up: a "20% of plot" chip over a
 * proportional bar. Replaces the old seven-star rating, which read as a
 * quality score (#7197); ★ is now reserved for favourites.
 */
export default function ShareBar({ share }: { share: number }) {
  const { t } = useTranslation();
  return (
    <span className={styles.shareBar}>
      <span className={styles.shareChip}>
        {t('plot.card.shareOfPlot', { pct: formatShare(share) })}
      </span>
      <ShareTrack share={share} />
    </span>
  );
}
