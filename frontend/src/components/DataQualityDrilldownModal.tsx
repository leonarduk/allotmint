import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import type { TimeseriesQualityPosition } from "../types";

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
    <div
      role="dialog"
      aria-modal="true"
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        background: "rgba(0,0,0,0.3)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <div
        style={{
          background: "var(--surface-card-bg, #fff)",
          color: "var(--surface-card-color, #111)",
          border: "1px solid var(--surface-card-border, #d9d9d9)",
          padding: "1rem",
          maxHeight: "80%",
          minWidth: "20rem",
          overflow: "auto",
        }}
      >
        <h3>
          {t("dataQuality.drilldown.title", {
            ticker: position.ticker,
            exchange: position.exchange,
          })}
        </h3>

        {hasGaps && (
          <div style={{ marginBottom: "1rem" }}>
            <h4 style={{ margin: "0 0 0.5rem 0" }}>{t("dataQuality.drilldown.gaps")}</h4>
            <ul style={{ margin: 0, paddingLeft: "1rem" }}>
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
          <div style={{ marginBottom: "1rem" }}>
            <h4 style={{ margin: "0 0 0.5rem 0" }}>{t("dataQuality.drilldown.duplicates")}</h4>
            <ul style={{ margin: 0, paddingLeft: "1rem" }}>
              {position.duplicate_dates.map((date) => (
                <li key={date}>{date}</li>
              ))}
            </ul>
          </div>
        )}

        {hasOutliers && (
          <div style={{ marginBottom: "1rem" }}>
            <h4 style={{ margin: "0 0 0.5rem 0" }}>{t("dataQuality.drilldown.outliers")}</h4>
            <table>
              <thead>
                <tr>
                  <th style={{ textAlign: "left", paddingRight: "1rem" }}>
                    {t("dataQuality.drilldown.date")}
                  </th>
                  <th style={{ textAlign: "right", paddingRight: "1rem" }}>
                    {t("dataQuality.drilldown.value")}
                  </th>
                  <th style={{ textAlign: "right" }}>{t("dataQuality.drilldown.zScore")}</th>
                </tr>
              </thead>
              <tbody>
                {position.outliers.map((outlier) => (
                  <tr key={outlier.date}>
                    <td style={{ paddingRight: "1rem" }}>{outlier.date}</td>
                    <td style={{ textAlign: "right", paddingRight: "1rem" }}>
                      {outlier.value.toFixed(2)}
                    </td>
                    <td style={{ textAlign: "right" }}>{outlier.z_score.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {!hasIssues && <p style={{ margin: 0 }}>{t("dataQuality.drilldown.noIssues")}</p>}

        <button onClick={onClose} style={{ marginTop: "1rem" }}>
          {t("dataQuality.drilldown.close")}
        </button>
      </div>
    </div>
  );
}

export default DataQualityDrilldownModal;
