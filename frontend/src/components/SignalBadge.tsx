import React from "react";

type Props = {
  action: string;
  onClick?: () => void;
};

export function SignalBadge({ action, onClick }: Props) {
  const lower = action.toLowerCase();
  const isBuy = lower === "buy";
  const color = isBuy ? "#bbf7d0" : "#fecaca"; // tailwind: green-200 / red-200
  return (
    <span
      onClick={onClick}
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
