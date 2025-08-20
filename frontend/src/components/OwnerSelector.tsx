import type {OwnerSummary} from "../types";
import {Selector} from "./Selector";
import {useTranslation} from "react-i18next";

type Props = {
  owners: OwnerSummary[];
  selected: string;
  onSelect: (owner: string) => void;
};

export function OwnerSelector({owners, selected, onSelect}: Props) {
  const {t} = useTranslation();
  return (
    <Selector
      label={t("owner.label")}
      value={selected}
      onChange={onSelect}
      options={owners.map((o) => ({value: o.owner, label: o.owner}))}
    />
  );
}
