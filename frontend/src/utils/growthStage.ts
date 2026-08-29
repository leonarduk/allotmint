export type GrowthStage = "seed" | "growing" | "harvest" | "unknown";

export interface GrowthStageInfo {
  stage: GrowthStage;
  icon: string;
  message: string;
}

/**
 * Determine the growth stage for a holding based on metrics.
 *
 * When `daysHeld` is null/undefined (no real acquisition date on record —
 * see #7220), this deliberately returns the distinct "unknown" stage rather
 * than falling through to "seed": a missing date is not evidence of a new
 * position, and every holding silently defaulting to the same stage is the
 * exact bug this guards against.
 */
export function getGrowthStage({
  daysHeld,
  currentPrice,
  targetPrice,
}: {
  daysHeld?: number | null;
  currentPrice?: number | null;
  targetPrice?: number | null;
}): GrowthStageInfo {
  if (
    targetPrice != null &&
    currentPrice != null &&
    currentPrice >= targetPrice
  ) {
    return {
      stage: "harvest",
      icon: "🍾",
      message: "Target met – consider selling.",
    };
  }
  if (daysHeld == null) {
    return {
      stage: "unknown",
      icon: "❔",
      message: "No acquisition date on record – growth stage unknown.",
    };
  }
  if (daysHeld >= 180) {
    return {
      stage: "harvest",
      icon: "🍾",
      message: "Long-term hold – review position.",
    };
  }
  if (daysHeld >= 30) {
    return {
      stage: "growing",
      icon: "🌿",
      message: "Growing – monitor performance.",
    };
  }
  return {
    stage: "seed",
    icon: "🌱",
    message: "New position – give it time to grow.",
  };
}

export default getGrowthStage;
