import type { CSSProperties } from 'react';
import { Link } from 'react-router-dom';
import styles from '../plot.module.css';
import { formatGbp, formatPct, growthStageMeta, type Crop } from '../plotModel';
import CropGlyph from './CropGlyph';
import StarRating from './StarRating';

interface CropCardProps {
  crop: Crop;
  /** Root of the plot routes, so the card can link to its detail screen. */
  basePath: string;
  favourite?: boolean;
  /** Omitted where the card is read-only, e.g. the hub's "biggest crops". */
  onToggleFavourite?: (ticker: string) => void;
}

/** Roster tile: one holding rendered as a collectable crop. */
export default function CropCard({
  crop,
  basePath,
  favourite = false,
  onToggleFavourite,
}: CropCardProps) {
  const stage = growthStageMeta(crop.stage);
  const cardStyle = { '--plot-crop-accent': stage.accent } as CSSProperties;

  return (
    <div className={styles.cropCardWrap} style={cardStyle}>
      {onToggleFavourite && (
        <button
          type="button"
          className={
            favourite
              ? `${styles.favouriteToggle} ${styles.favouriteToggleOn}`
              : styles.favouriteToggle
          }
          aria-pressed={favourite}
          aria-label={
            favourite
              ? `Remove ${crop.ticker} from favourites`
              : `Add ${crop.ticker} to favourites`
          }
          onClick={() => onToggleFavourite(crop.ticker)}
        >
          <span aria-hidden="true">★</span>
        </button>
      )}
      <Link
        to={`${basePath}/crops/${encodeURIComponent(crop.id)}`}
        className={styles.cropCard}
      >
        <span className={styles.cropGlyph}>
          <CropGlyph
            ticker={crop.ticker}
            sector={crop.sector}
            stage={crop.stage}
          />
        </span>
        <StarRating value={crop.stars} />
        <span className={styles.cropTicker}>{crop.ticker}</span>
        <span className={styles.cropName}>{crop.name}</span>
        <span className={styles.cropStageChip}>{stage.label}</span>
        <span className={styles.cropValue}>{formatGbp(crop.valueGbp)}</span>
        <span className={crop.gainPct >= 0 ? styles.gain : styles.loss}>
          {formatPct(crop.gainPct)}
        </span>
      </Link>
    </div>
  );
}
