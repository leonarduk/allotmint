type Action = "buy" | "sell" | "BUY" | "SELL";
type Props = {
  action: Action;
  reason?: string;
  confidence?: number;
  rationale?: string;
  onClick?: () => void;
};

export function SignalBadge({ action, reason, confidence, rationale, onClick }: Props) {
  const isBuy = action.toLowerCase() === "buy";
  const label = isBuy ? "Buy" : "Sell";
  const color = isBuy ? "#bbf7d0" : "#fecaca"; // tailwind: green-200 / red-200
  const details = [
    reason,
    confidence != null ? `Confidence: ${(confidence * 100).toFixed(0)}%` : undefined,
    rationale,
  ]
    .filter(Boolean)
    .join("\n");
  return (
    <button
      type="button"
      onClick={onClick}
      title={details || undefined}
      aria-label={
        onClick ? `${label} signal — select to view reason and confidence` : label
      }
      style={{
        backgroundColor: color,
        padding: "2px 6px",
        borderRadius: "4px",
        border: "none",
        font: "inherit",
        cursor: onClick ? "pointer" : "default",
        fontWeight: 500,
      }}
    >
      {label}
    </button>
  );
}
