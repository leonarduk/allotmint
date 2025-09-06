import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter, Routes, Route, useParams } from "react-router-dom";
import { describe, it, expect, vi } from "vitest";

vi.mock("../api", () => ({
  searchInstruments: vi.fn(),
}));

import InstrumentSearchBar from "./InstrumentSearchBar";
import { searchInstruments } from "../api";

function ResearchPage() {
  const { ticker } = useParams();
  return <div data-testid="research-page">{ticker}</div>;
}

describe("InstrumentSearchBar", () => {
  it("searches with filters and navigates on selection", async () => {
    const searchMock = searchInstruments as unknown as vi.Mock;
    searchMock.mockResolvedValue([{ ticker: "AAA", name: "AAA Corp" }]);

    render(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={<InstrumentSearchBar />} />
          <Route path="/research/:ticker" element={<ResearchPage />} />
        </Routes>
      </MemoryRouter>
    );

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

    fireEvent.mouseDown(screen.getByText("AAA — AAA Corp"));
    expect(await screen.findByTestId("research-page")).toHaveTextContent("AAA");
  });
});

