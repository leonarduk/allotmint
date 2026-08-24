import type { CSSProperties } from 'react';
import { Link } from 'react-router-dom';
import styles from '../plot.module.css';
import { cropGlyph } from '../cropGlyph';
import { formatGbp, formatPct, growthStageMeta, type Crop } from '../plotModel';
import StarRating from './StarRating';

interface CropCardProps {
  crop: Crop;
  /** Root of the plot routes, so the card can link to its detail screen. */
  basePath: string;
}

/** Roster tile: one holding rendered as a collectable crop. */
export default function CropCard({ crop, basePath }: CropCardProps) {
  const stage = growthStageMeta(crop.stage);
  const cardStyle = { '--plot-crop-accent': stage.accent } as CSSProperties;

  return (
    <Link
      to={`${basePath}/crops/${encodeURIComponent(crop.ticker)}`}
      className={styles.cropCard}
      style={cardStyle}
    >
      <span className={styles.cropGlyph} aria-hidden="true">
        {cropGlyph(crop.ticker, crop.sector)}
      </span>
      <StarRating value={crop.stars} />
      <span className={styles.cropTicker}>{crop.ticker}</span>
      <span className={styles.cropName}>{crop.name}</span>
      <span className={styles.cropStageChip}>
        <span aria-hidden="true">{stage.icon}</span> {stage.label}
      </span>
      <span className={styles.cropValue}>{formatGbp(crop.valueGbp)}</span>
      <span className={crop.gainPct >= 0 ? styles.gain : styles.loss}>
        {formatPct(crop.gainPct)}
      </span>
    </Link>
  );
}
