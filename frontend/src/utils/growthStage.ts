export type GrowthStage = "seed" | "growing" | "harvest";

export interface GrowthStageInfo {
  stage: GrowthStage;
  icon: string;
  message: string;
}

/**
 * Determine the growth stage for a holding based on metrics.
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
  if (daysHeld != null && daysHeld >= 180) {
    return {
      stage: "harvest",
      icon: "🍾",
      message: "Long-term hold – review position.",
    };
  }
  if (daysHeld != null && daysHeld >= 30) {
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
