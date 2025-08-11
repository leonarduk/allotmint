import { useEffect, useState } from "react";
import { OwnerSelector } from "../components/OwnerSelector";
import { PerformanceDashboard } from "../components/PerformanceDashboard";
import type { OwnerSummary } from "../types";

interface Props {
  owners: OwnerSummary[];
}

export default function PerformancePage({ owners }: Props) {
  const [selectedOwner, setSelectedOwner] = useState("");

  useEffect(() => {
    if (!selectedOwner && owners.length) {
      setSelectedOwner(owners[0].owner);
    }
  }, [owners, selectedOwner]);

  return (
    <>
      <OwnerSelector
        owners={owners}
        selected={selectedOwner}
        onSelect={setSelectedOwner}
      />
      <PerformanceDashboard owner={selectedOwner} />
    </>
  );
}
