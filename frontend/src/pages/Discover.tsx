import { useState } from "react";
import { CriteriaBuilder } from "../components/CriteriaBuilder";
import type { Criterion } from "../components/CriteriaBuilder";
import { Sparkline } from "../components/Sparkline";

/**
 * Minimal page combining `CriteriaBuilder` and `Sparkline` components. It is
 * primarily used for unit testing in this repository and does not expose any
 * additional behaviour beyond the rendered components.
 */
export function Discover() {
  const [criteria, setCriteria] = useState<Criterion[]>([]);
  return (
    <div>
      <h1>Discover</h1>
      <CriteriaBuilder criteria={criteria} onChange={setCriteria} />
      {/* Static data is sufficient for testing purposes */}
      <Sparkline data={[1, 3, 2]} />
    </div>
  );
}

export default Discover;
