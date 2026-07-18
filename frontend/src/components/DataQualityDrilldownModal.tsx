import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import type { TimeseriesQualityPosition } from "../types";
import styles from "../styles/dataQualityDrilldownModal.module.css";

interface Props {
  position: TimeseriesQualityPosition;
  onClose: () => void;
}

export function DataQualityDrilldownModal({ position, onClose }: Props) {
  const { t } = useTranslation();
  const hasGaps = position.gaps.length > 0;
  const hasDuplicates = position.duplicate_dates.length > 0;
  const hasOutliers = position.outliers.length > 0;
  const hasIssues = hasGaps || hasDuplicates || hasOutliers;

  // Keep a stable ref to onClose so the keydown listener is registered only
  // once (on mount) and never needs to be removed/re-added when the parent
  // re-renders with a new inline callback reference.
  const onCloseRef = useRef(onClose);
  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onCloseRef.current();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, []);

  return (
    <div role="dialog" aria-modal="true" className={styles.overlay}>
      <div className={styles.modal}>
        <h3>
          {t("dataQuality.drilldown.title", {
            ticker: position.ticker,
            exchange: position.exchange,
          })}
        </h3>

        {hasGaps && (
          <div className={styles.section}>
            <h4 className={styles.sectionHeading}>{t("dataQuality.drilldown.gaps")}</h4>
            <ul className={styles.list}>
              {position.gaps.map((gap) => (
                <li key={`${gap.start}-${gap.end}`}>
                  {gap.start} – {gap.end} (
                  {t("dataQuality.drilldown.missingDays", { count: gap.missing_business_days })})
                </li>
              ))}
            </ul>
          </div>
        )}

        {hasDuplicates && (
          <div className={styles.section}>
            <h4 className={styles.sectionHeading}>{t("dataQuality.drilldown.duplicates")}</h4>
            <ul className={styles.list}>
              {position.duplicate_dates.map((date) => (
                <li key={date}>{date}</li>
              ))}
            </ul>
          </div>
        )}

        {hasOutliers && (
          <div className={styles.section}>
            <h4 className={styles.sectionHeading}>{t("dataQuality.drilldown.outliers")}</h4>
            <table>
              <thead>
                <tr>
                  <th className={styles.headerCellLeft}>{t("dataQuality.drilldown.date")}</th>
                  <th className={styles.headerCellRight}>{t("dataQuality.drilldown.value")}</th>
                  <th className={styles.headerCellRightLast}>
                    {t("dataQuality.drilldown.zScore")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {position.outliers.map((outlier) => (
                  <tr key={outlier.date}>
                    <td className={styles.cellRight}>{outlier.date}</td>
                    <td className={styles.cellRightAligned}>{outlier.value.toFixed(2)}</td>
                    <td className={styles.cellRightAlignedLast}>
                      {outlier.z_score.toFixed(2)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {!hasIssues && <p className={styles.noIssues}>{t("dataQuality.drilldown.noIssues")}</p>}

        <button onClick={onClose} className={styles.closeButton}>
          {t("dataQuality.drilldown.close")}
        </button>
      </div>
    </div>
  );
}

export default DataQualityDrilldownModal;
