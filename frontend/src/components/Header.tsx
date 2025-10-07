import { useTranslation } from "react-i18next";

import { formatDateISO } from "../lib/date";

interface Props {
  asOf?: string | null;
  tradesThisMonth?: number | null;
  tradesRemaining?: number | null;
}

export function Header({ asOf, tradesThisMonth, tradesRemaining }: Props) {
  const { t } = useTranslation();

  if (asOf == null || tradesThisMonth == null || tradesRemaining == null) {
    return null;
  }

  const date = new Date(asOf);
  if (Number.isNaN(date.getTime())) {
    return null;
  }

  return (
    <div style={{ marginBottom: "1rem" }}>
      {t("asOf", {
        date: formatDateISO(date),
        trades: tradesThisMonth,
        remaining: tradesRemaining,
      })}
    </div>
  );
}
