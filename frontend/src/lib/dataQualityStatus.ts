import type { TimeseriesQualityPosition } from "../types";

export type QualityStatus = "green" | "amber" | "red";

/**
 * Derives a tri-color RAG status from counts the backend already computed
 * (see #4897's compute_quality). This is a display-only bucketing of
 * existing counts, not a reimplementation of gap/outlier detection.
 */
export function getQualityStatus(
  position: Pick<TimeseriesQualityPosition, "gap_count" | "duplicate_dates" | "outliers">,
): QualityStatus {
  if (position.duplicate_dates.length > 0 || position.outliers.length > 0) {
    return "red";
  }
  if (position.gap_count > 0) {
    return "amber";
  }
  return "green";
}
