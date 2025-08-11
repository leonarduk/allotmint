import { useEffect, useState } from "react";
import { GroupSelector } from "../components/GroupSelector";
import { GroupPortfolioView } from "../components/GroupPortfolioView";
import { ComplianceWarnings } from "../components/ComplianceWarnings";
import type { GroupSummary } from "../types";

interface Props {
  groups: GroupSummary[];
  relativeView: boolean;
}

export default function GroupPage({ groups, relativeView }: Props) {
  const [selectedGroup, setSelectedGroup] = useState("");

  useEffect(() => {
    if (!selectedGroup && groups.length) {
      setSelectedGroup(groups[0].slug);
    }
  }, [groups, selectedGroup]);

  return (
    <>
      <GroupSelector
        groups={groups}
        selected={selectedGroup}
        onSelect={setSelectedGroup}
      />
      <ComplianceWarnings
        owners={groups.find((g) => g.slug === selectedGroup)?.members ?? []}
      />
      <GroupPortfolioView slug={selectedGroup} relativeView={relativeView} />
    </>
  );
}
