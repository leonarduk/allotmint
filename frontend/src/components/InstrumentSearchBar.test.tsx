import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi } from "vitest";
import InstrumentSearchBar from "./InstrumentSearchBar";

vi.mock("../api", () => ({
  searchInstruments: vi.fn(),
}));
import { searchInstruments } from "../api";

describe("InstrumentSearchBar", () => {
  it("shows error when search fails", async () => {
    (searchInstruments as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("boom"));

    render(
      <MemoryRouter>
        <InstrumentSearchBar />
      </MemoryRouter>,
    );

    const user = userEvent.setup();
    const input = screen.getByRole("textbox", { name: /search instruments/i });
    await user.type(input, "ab");

    expect(await screen.findByRole("alert")).toHaveTextContent("Search failed");
  });
});
