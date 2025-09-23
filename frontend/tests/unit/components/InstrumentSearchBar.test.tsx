import userEvent from "@testing-library/user-event";
import InstrumentSearchBar from "@/components/InstrumentSearchBar";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter, Routes, Route, useParams } from "react-router-dom";
import { describe, it, expect, vi } from "vitest";
import { searchInstruments } from "@/api";
import i18n from "@/i18n";

vi.mock("@/api", () => ({
  searchInstruments: vi.fn(),
}));


function ResearchPage() {
  const { ticker } = useParams();
  return <div data-testid="research-page">{ticker}</div>;
}

describe("InstrumentSearchBar", () => {
  it("searches with filters and navigates on selection", async () => {
    const searchMock = searchInstruments as unknown as vi.Mock;
    searchMock.mockResolvedValue([{ ticker: "AAA", name: "AAA Corp" }]);

    const user = userEvent.setup();

    render(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={<InstrumentSearchBar />} />
          <Route path="/research/:ticker" element={<ResearchPage />} />
        </Routes>
      </MemoryRouter>
    );

    const researchLabel = i18n.t("app.research");
    const researchButton = screen.getByRole("button", { name: researchLabel });
    expect(researchButton).toBeInTheDocument();
    expect(
      screen.queryByLabelText(/Search instruments/i)
    ).not.toBeInTheDocument();

    await user.click(researchButton);

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

    fireEvent.mouseDown(screen.getByText("AAA — AAA Corp"));
    expect(await screen.findByTestId("research-page")).toHaveTextContent("AAA");
  });
});

