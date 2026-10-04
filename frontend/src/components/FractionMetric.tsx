import { useTranslation } from "react-i18next";
import { percent } from "../lib/money";
import { classifyMetric, type PlausibleRange } from "../lib/metricPlausibility";

type FractionMetricProps = {
  /** The metric as a FRACTION (0.0596 = 5.96%), exactly as the API returns it. */
  value: number | null | undefined;
  range: PlausibleRange;
  testId?: string;
};

/**
 * Render a fraction-unit metric as a percentage, or "N/A" when unusable.
 * Implausible values get an "unreliable" tooltip and are never rescaled
 * (#8570).
 */
export function FractionMetric({ value, range, testId }: FractionMetricProps) {
  const { t, i18n } = useTranslation();
  const na = t("dashboard.metricNotAvailable", "N/A");
  const state = classifyMetric(value, range);
  if (state === "missing") {
    return <span data-testid={testId}>{na}</span>;
  }
  if (state === "unreliable") {
    return (
      <span
        data-testid={testId}
        data-unreliable="true"
        title={t(
          "dashboard.metricUnreliable",
          "This calculation looks unreliable (the value is outside a plausible range), so it is not shown.",
        )}
      >
        {na}
      </span>
    );
  }
  return (
    <span data-testid={testId}>{percent((value as number) * 100, 2, i18n.language)}</span>
  );
}

export default FractionMetric;
