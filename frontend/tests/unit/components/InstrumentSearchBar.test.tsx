import userEvent from "@testing-library/user-event";
import { InstrumentSearchBar } from "@/components/InstrumentSearchBar";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi } from "vitest";
import { searchInstruments } from "@/api";
import i18n from "@/i18n";

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
});

