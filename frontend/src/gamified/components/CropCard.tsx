import type { CSSProperties } from 'react';
import { useTranslation } from 'react-i18next';
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
  const { t } = useTranslation();
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
              ? t('plot.card.removeFavourite', { ticker: crop.ticker })
              : t('plot.card.addFavourite', { ticker: crop.ticker })
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
        {/* The same instrument can legitimately sit in more than one bed
            (ISA and SIPP both holding ERNS.L, for example); without this the
            two cards are visually identical and there's no way to tell them
            apart on the roster or hub (#7212, bed-label half only — no
            cross-bed aggregation here, see the issue for why). */}
        <span className={styles.cropBed}>{crop.bedName}</span>
        <span className={styles.cropStageChip}>{stage.label}</span>
        <span className={styles.cropValue}>{formatGbp(crop.valueGbp)}</span>
        {/* A crop with no recorded intraday move shows "no data" rather than
            a confident +0.0%, so a genuinely flat day stays distinguishable
            from a missing figure (#vigour-constant). */}
        <span className={(crop.gainPct ?? 0) >= 0 ? styles.gain : styles.loss}>
          {formatPct(crop.gainPct)}
        </span>
        <span className={styles.cropDayChange}>
          {crop.hasMove
            ? t('plot.card.today', { pct: formatPct(crop.dayChangePct) })
            : t('plot.card.noDataToday')}
        </span>
      </Link>
    </div>
  );
}
