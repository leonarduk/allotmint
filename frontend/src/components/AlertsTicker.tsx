import { useState } from "react";
import type { Alert } from "../types";

interface AlertsTickerProps {
  alerts: Alert[];
  speed?: number; // animation duration in seconds
  pauseOnHover?: boolean;
}

export function AlertsTicker({ alerts, speed = 20, pauseOnHover = true }: AlertsTickerProps) {
  const [paused, setPaused] = useState(false);
  if (alerts.length === 0) return null;

  const animationDuration = `${speed}s`;

  return (
    <div
      className="overflow-hidden whitespace-nowrap"
      onMouseEnter={() => pauseOnHover && setPaused(true)}
      onMouseLeave={() => pauseOnHover && setPaused(false)}
    >
      <div
        style={{
          display: "inline-block",
          paddingLeft: "100%",
          animation: `marquee ${animationDuration} linear infinite`,
          animationPlayState: paused ? "paused" : "running",
        }}
      >
        {alerts.map((a, i) => (
          <span key={i} style={{ marginRight: "2rem" }}>
            <strong>{a.ticker}</strong>: {a.message}
          </span>
        ))}
      </div>
      <style>
        {`
          @keyframes marquee {
            0% { transform: translateX(0); }
            100% { transform: translateX(-100%); }
          }
        `}
      </style>
    </div>
  );
}
