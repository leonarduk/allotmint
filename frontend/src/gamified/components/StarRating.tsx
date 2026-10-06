import { useTranslation } from 'react-i18next';
import styles from '../plot.module.css';

interface StarRatingProps {
  /** Filled stars, 0–max. */
  value: number;
  max?: number;
}

/** Seven-star rating showing how much of the plot a crop occupies. */
export default function StarRating({ value, max = 7 }: StarRatingProps) {
  const { t } = useTranslation();
  const filled = Math.max(0, Math.min(max, Math.round(value)));
  return (
    <span className={styles.stars} aria-label={t('plot.stars', { filled, max })}>
      {Array.from({ length: max }, (_, index) => (
        <span
          key={index}
          aria-hidden="true"
          className={index < filled ? styles.starOn : styles.star}
        >
          ★
        </span>
      ))}
    </span>
  );
}
