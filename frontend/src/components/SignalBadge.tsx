type Action = "buy" | "sell";
type Props = {
  action: Action;
  reason?: string;
  onClick?: () => void;
};

export function SignalBadge({ action, reason, onClick }: Props) {
  const isBuy = action === "buy";
  const color = isBuy ? "#bbf7d0" : "#fecaca"; // tailwind: green-200 / red-200
  return (
    <span
      onClick={onClick}
      title={reason}
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
