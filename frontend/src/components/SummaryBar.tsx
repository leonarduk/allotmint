import { useTranslation } from "react-i18next";
import { OwnerSelector } from "./OwnerSelector";
import type { OwnerSummary } from "../types";

interface Props {
  owners: OwnerSummary[];
  owner: string;
  onOwnerChange: (owner: string) => void;
  onRefresh: () => void;
}

export default function SummaryBar({ owners, owner, onOwnerChange, onRefresh }: Props) {
  const { t } = useTranslation();
  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        marginBottom: "1rem",
        gap: "1rem",
      }}
    >
      <OwnerSelector owners={owners} selected={owner} onSelect={onOwnerChange} />
      <button onClick={onRefresh}>{t("watchlist.refresh")}</button>
    </div>
  );
}
