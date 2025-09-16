import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi } from "vitest";

import i18n from "../i18n";

vi.mock("../api", () => ({
  listInstrumentMetadata: vi.fn().mockResolvedValue([
    { ticker: "AAA.L", name: "Alpha", region: "EU", sector: "Tech" },
    { ticker: "BBB.N", name: "Beta", region: "US", sector: "Finance" },
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
    fireEvent.click(screen.getAllByRole("button", { name: /save/i })[0]);
    await waitFor(() => expect(updateInstrumentMetadata).toHaveBeenCalled());
  });

  it("filters rows based on search", async () => {
    render(
      <MemoryRouter>
        <InstrumentAdmin />
      </MemoryRouter>,
    );
    expect(await screen.findByDisplayValue("AAA")).toBeInTheDocument();
    expect(screen.getByDisplayValue("BBB")).toBeInTheDocument();

    const searchPlaceholder = i18n.t("instrumentadmin.searchPlaceholder");

    fireEvent.change(
      screen.getByPlaceholderText(searchPlaceholder),
      { target: { value: "beta" } },
    );

    await waitFor(() => {
      expect(screen.queryByDisplayValue("AAA")).not.toBeInTheDocument();
      expect(screen.getByDisplayValue("BBB")).toBeInTheDocument();
    });
  });
});

