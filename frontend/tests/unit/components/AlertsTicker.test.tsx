import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AlertsTicker } from "@/components/AlertsTicker";

const sampleAlerts = [
  { ticker: "AAA", change_pct: 1, message: "First alert", timestamp: "2024-01-01" },
  { ticker: "BBB", change_pct: 2, message: "Second alert", timestamp: "2024-01-02" },
];

describe("AlertsTicker", () => {
  it("renders alert messages", () => {
    render(<AlertsTicker alerts={sampleAlerts} speed={10} pauseOnHover={false} />);
    expect(screen.getByText(/AAA/)).toBeInTheDocument();
    expect(screen.getByText(/BBB/)).toBeInTheDocument();
  });
});
