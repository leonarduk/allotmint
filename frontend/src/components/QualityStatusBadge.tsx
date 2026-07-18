import { useTranslation } from "react-i18next";
import type { QualityStatus } from "../lib/dataQualityStatus";

const STATUS_COLORS: Record<QualityStatus, { bg: string; fg: string }> = {
  green: { bg: "#1e7e34", fg: "#fff" },
  amber: { bg: "#b8860b", fg: "#fff" },
  red: { bg: "#b02a37", fg: "#fff" },
};

interface Props {
  status: QualityStatus;
}

export function QualityStatusBadge({ status }: Props) {
  const { t } = useTranslation();
  const colors = STATUS_COLORS[status];
  return (
    <span
      role="status"
      style={{
        display: "inline-block",
        padding: "0.15rem 0.6rem",
        borderRadius: "999px",
        fontSize: "0.75rem",
        fontWeight: 600,
        backgroundColor: colors.bg,
        color: colors.fg,
      }}
    >
      {t(`dataQuality.status.${status}`)}
    </span>
  );
}

export default QualityStatusBadge;
