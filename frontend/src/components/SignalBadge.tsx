type Action = "buy" | "sell";
type Props = {
  action: Action;
  reason?: string;
  confidence?: number;
  rationale?: string;
  onClick?: () => void;
};

export function SignalBadge({ action, reason, confidence, rationale, onClick }: Props) {
  const isBuy = action === "buy";
  const color = isBuy ? "#bbf7d0" : "#fecaca"; // tailwind: green-200 / red-200
  const details = [
    reason,
    confidence != null ? `Confidence: ${(confidence * 100).toFixed(0)}%` : undefined,
    rationale,
  ]
    .filter(Boolean)
    .join("\n");
  return (
    <span
      onClick={onClick}
      title={details || undefined}
      style={{
        backgroundColor: color,
        padding: "2px 6px",
        borderRadius: "4px",
        cursor: onClick ? "pointer" : "default",
        fontWeight: 500,
      }}
    >
      {isBuy ? "Buy" : "Sell"}
    </span>
  );
}
