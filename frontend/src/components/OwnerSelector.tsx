import type { OwnerSummary } from "../types";
import { Selector } from "./Selector";
import { useTranslation } from "react-i18next";
import { useCallback, memo } from "react";
import type { ChangeEventHandler } from "react";

type Props = {
  owners: OwnerSummary[];
  selected: string;
  onSelect: (owner: string) => void;
};

export const OwnerSelector = memo(function OwnerSelector({
  owners,
  selected,
  onSelect,
}: Props) {
  const { t } = useTranslation();
  const handleChange = useCallback<ChangeEventHandler<HTMLSelectElement>>(
    (e) => onSelect(e.target.value),
    [onSelect],
  );

  return (
    <Selector
      label={t("owner.label")}
      value={selected}
      onChange={handleChange}
      options={owners.map((o) => ({
        value: o.owner,
        label: o.full_name?.trim() ? o.full_name : o.owner,
      }))}
    />
  );
});

