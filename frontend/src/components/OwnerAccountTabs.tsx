import type { CSSProperties } from "react";
import { useTranslation } from "react-i18next";
import type { OwnerTab } from "../lib/ownerTabs";

const tabStyle = (active: boolean): CSSProperties => ({
  padding: "0.5rem 0.75rem",
  borderRadius: "4px",
  border: "1px solid var(--tab-border)",
  backgroundColor: active ? "var(--tab-active-bg)" : "transparent",
  color: active ? "var(--tab-active-text)" : "inherit",
  cursor: "pointer",
});

const rowStyle: CSSProperties = {
  display: "flex",
  gap: "0.5rem",
  marginBottom: "1rem",
  flexWrap: "wrap",
};

type Props = {
  ownerTabs: OwnerTab[];
  activeOwner: string | null;
  activeAccountType: string | null;
  onOwnerChange: (owner: string | null) => void;
  onAccountTypeChange: (accountType: string | null) => void;
};

/** "All positions / <owner>…" tabs, plus "All accounts / <type>…" once an owner is picked. */
export function OwnerAccountTabs({
  ownerTabs,
  activeOwner,
  activeAccountType,
  onOwnerChange,
  onAccountTypeChange,
}: Props) {
  const { t } = useTranslation();
  const accountTypes = ownerTabs.find((tab) => tab.value === activeOwner)?.accountTypes;
  return (
    <>
      <div role="tablist" aria-label={t("query.owners")} style={rowStyle}>
        <button
          type="button"
          role="tab"
          aria-selected={activeOwner === null}
          onClick={() => onOwnerChange(null)}
          style={tabStyle(activeOwner === null)}
        >
          {t("group.allPositions")}
        </button>
        {ownerTabs.map((tab) => (
          <button
            key={tab.value}
            type="button"
            role="tab"
            aria-selected={activeOwner === tab.value}
            onClick={() => onOwnerChange(tab.value)}
            style={tabStyle(activeOwner === tab.value)}
          >
            {tab.label}
          </button>
        ))}
      </div>
      {activeOwner && accountTypes && (
        <div role="tablist" aria-label={`${activeOwner} accounts`} style={rowStyle}>
          <button
            type="button"
            role="tab"
            aria-selected={activeAccountType === null}
            onClick={() => onAccountTypeChange(null)}
            style={tabStyle(activeAccountType === null)}
          >
            {t("group.allAccounts")}
          </button>
          {accountTypes.map((type) => (
            <button
              key={type}
              type="button"
              role="tab"
              aria-selected={activeAccountType === type}
              onClick={() => onAccountTypeChange(type)}
              style={tabStyle(activeAccountType === type)}
            >
              {type}
            </button>
          ))}
        </div>
      )}
    </>
  );
}
