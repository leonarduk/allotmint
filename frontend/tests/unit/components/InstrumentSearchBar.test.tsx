import userEvent from "@testing-library/user-event";
import {
  InstrumentSearchBar,
  InstrumentSearchBarToggle,
} from "@/components/InstrumentSearchBar";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi } from "vitest";
import { searchInstruments } from "@/api";

vi.mock("@/api", () => ({
  searchInstruments: vi.fn(),
}));


describe("InstrumentSearchBar", () => {
  it("searches with filters and navigates on selection", async () => {
    const searchMock = searchInstruments as unknown as vi.Mock;
    searchMock.mockResolvedValue([{ ticker: "AAA", name: "AAA Corp" }]);
    const onNavigate = vi.fn();

    const user = userEvent.setup();

    render(
      <MemoryRouter>
        <InstrumentSearchBar onNavigate={onNavigate} />
      </MemoryRouter>
    );

    expect(
      await screen.findByLabelText(/Search instruments/i)
    ).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/Filter by sector/i), {
      target: { value: "Energy" },
    });
    fireEvent.change(screen.getByLabelText(/Filter by region/i), {
      target: { value: "Europe" },
    });

    fireEvent.change(screen.getByLabelText(/Search instruments/i), {
      target: { value: "AA" },
    });
    await new Promise((r) => setTimeout(r, 350));

    expect(await screen.findByText("AAA — AAA Corp")).toBeInTheDocument();
    expect(searchMock).toHaveBeenCalledWith("AA", "Energy", "Europe", expect.anything());

    await user.click(screen.getByText("AAA — AAA Corp"));
    expect(onNavigate).toHaveBeenCalled();
  });

  it("does not emit duplicate-key warnings for duplicate result tickers (#6505)", async () => {
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const searchMock = searchInstruments as unknown as vi.Mock;
    searchMock.mockResolvedValue([
      { ticker: "CASH", name: "Cash GBP" },
      { ticker: "CASH", name: "Cash L" },
    ]);
    const onNavigate = vi.fn();

    render(
      <MemoryRouter>
        <InstrumentSearchBar onNavigate={onNavigate} />
      </MemoryRouter>
    );

    fireEvent.change(screen.getByLabelText(/Search instruments/i), {
      target: { value: "CA" },
    });
    await new Promise((r) => setTimeout(r, 350));

    expect(await screen.findAllByText(/CASH —/)).toHaveLength(2);
    const keyWarnings = errorSpy.mock.calls.filter((args) =>
      String(args[0]).includes("same key")
    );
    expect(keyWarnings).toEqual([]);
    errorSpy.mockRestore();
  });

  // #7205: the header's search toggle previously reused the "Research" menu
  // label as its accessible name, which reads as a page name rather than a
  // search control — screen reader users had no indication this icon opens
  // a search box. It's also distinct from the "Search instruments" input
  // label it reveals (#7223), so opening the panel doesn't leave a button
  // and an input sharing one accessible name.
  it("labels the header search toggle as search, not as the Research menu entry", () => {
    render(
      <MemoryRouter>
        <InstrumentSearchBarToggle />
      </MemoryRouter>
    );

    expect(
      screen.getByRole("button", { name: "Open instrument search" })
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Research" })
    ).not.toBeInTheDocument();
  });
});
