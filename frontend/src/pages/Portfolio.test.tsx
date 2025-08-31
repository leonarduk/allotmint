import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import Portfolio from "./Portfolio";
import * as api from "../api";

vi.mock("../api");
const mockGetPortfolio = vi.mocked(api.getPortfolio);

describe("Portfolio page", () => {
  it("fetches and displays portfolio data", async () => {
    mockGetPortfolio.mockResolvedValueOnce({ owner: "alice", as_of: "2024-01-01", accounts: [] } as any);
    render(<Portfolio />);
    await waitFor(() => expect(mockGetPortfolio).toHaveBeenCalledWith("alice"));
    expect(await screen.findByTestId("owner-name")).toHaveTextContent("alice");
  });
});
