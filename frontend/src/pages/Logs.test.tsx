import { render, screen } from "@testing-library/react";
import { vi } from "vitest";
import Logs from "./Logs";

vi.mock("../api", () => ({ API_BASE: "" }));

describe("Logs page", () => {
  it("fetches and displays log text", async () => {
    const sample = "line1\nline2";
    global.fetch = vi
      .fn()
      .mockResolvedValue({ ok: true, text: () => Promise.resolve(sample) } as any);
    render(<Logs />);
    expect(await screen.findByText(/line2/)).toBeInTheDocument();
  });
});
