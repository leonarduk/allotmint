import React from "react";

interface Props {
  tradesThisMonth?: number | null;
  tradesRemaining?: number | null;
}

export function Header({ tradesThisMonth, tradesRemaining }: Props) {
  if (tradesThisMonth == null || tradesRemaining == null) return null;
  return (
    <div style={{ marginBottom: "1rem" }}>
      Trades this month: {tradesThisMonth} / 20 (Remaining: {tradesRemaining})
    </div>
  );
}
