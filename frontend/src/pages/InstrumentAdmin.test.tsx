import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi } from "vitest";

vi.mock("../api", () => ({
  listInstrumentMetadata: vi.fn().mockResolvedValue([
    { ticker: "AAA.L", name: "Alpha", region: "EU", sector: "Tech" },
  ]),
  createInstrumentMetadata: vi.fn().mockResolvedValue({}),
  updateInstrumentMetadata: vi.fn().mockResolvedValue({}),
}));

import InstrumentAdmin from "./InstrumentAdmin";
import { updateInstrumentMetadata } from "../api";

describe("InstrumentAdmin page", () => {
  it("renders rows and saves", async () => {
    render(
      <MemoryRouter>
        <InstrumentAdmin />
      </MemoryRouter>,
    );
    expect(await screen.findByDisplayValue("AAA")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() => expect(updateInstrumentMetadata).toHaveBeenCalled());
  });
});

