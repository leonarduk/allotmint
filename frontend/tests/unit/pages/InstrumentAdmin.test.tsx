import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi } from "vitest";

import i18n from "@/i18n";

vi.mock("@/api", () => ({
    listInstrumentMetadata: vi.fn().mockResolvedValue([,
    {
    ticker: "AAA.L",
    name: "Alpha",
    region: "EU",
    sector: "Tech",
    grouping: "ISA",
    },
    {
    ticker: "BBB.N",
    name: "Beta",
    region: "US",
    sector: "Finance",
    grouping: "GIA",
    },
    ]),
    createInstrumentMetadata: vi.fn().mockResolvedValue({}),
    updateInstrumentMetadata: vi.fn().mockResolvedValue({}),
    getCachedGroupInstruments: undefined,
}));

import InstrumentAdmin from "@/pages/InstrumentAdmin";
import { createInstrumentMetadata, updateInstrumentMetadata } from "@/api";

describe("InstrumentAdmin page", () => {

  it("renders rows and saves grouping updates", async () => {
    render(
      <MemoryRouter>
        <InstrumentAdmin />
      </MemoryRouter>,
    );
    expect(await screen.findByDisplayValue("AAA")).toBeInTheDocument();
    const groupingInput = screen.getByDisplayValue("ISA");
    fireEvent.change(groupingInput, { target: { value: "ISA+" } });
    fireEvent.click(screen.getAllByRole("button", { name: /save/i })[0]);
    await waitFor(() =>
      expect(updateInstrumentMetadata).toHaveBeenCalledWith(
        "AAA",
        "L",
        expect.objectContaining({ grouping: "ISA+" }),
      ),
    );
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

  it("creates new instruments with grouping", async () => {
    render(
      <MemoryRouter>
        <InstrumentAdmin />
      </MemoryRouter>,
    );

    expect(await screen.findByDisplayValue("AAA")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /add instrument/i }));

    await waitFor(() => expect(screen.getAllByRole("row")).toHaveLength(4));
    const dataRows = screen.getAllByRole("row").slice(1);
    const newRow = dataRows.find((row) => {
      const [tickerField] = within(row).getAllByRole("textbox");
      return (tickerField as HTMLInputElement).value === "";
    });
    expect(newRow).toBeDefined();
    const inputs = within(newRow as HTMLElement).getAllByRole("textbox");
    const [tickerInput, exchangeInput, nameInput, regionInput, sectorInput, groupingInput] =
      inputs;

    fireEvent.change(exchangeInput, { target: { value: "L" } });
    fireEvent.change(nameInput, { target: { value: "Gamma" } });
    fireEvent.change(regionInput, { target: { value: "UK" } });
    fireEvent.change(sectorInput, { target: { value: "Utilities" } });
    fireEvent.change(groupingInput, { target: { value: "Income" } });
    fireEvent.change(tickerInput, { target: { value: "CCC" } });

    const updatedTickerInput = await screen.findByDisplayValue("CCC");
    const updatedRow = updatedTickerInput.closest("tr");
    expect(updatedRow).not.toBeNull();
    const [
      tickerField,
      exchangeField,
      nameField,
      regionField,
      sectorField,
      groupingField,
    ] = within(updatedRow as HTMLElement).getAllByRole("textbox");

    expect((tickerField as HTMLInputElement).value).toBe("CCC");
    expect((exchangeField as HTMLInputElement).value).toBe("L");
    expect((nameField as HTMLInputElement).value).toBe("Gamma");
    expect((regionField as HTMLInputElement).value).toBe("UK");
    expect((sectorField as HTMLInputElement).value).toBe("Utilities");
    expect((groupingField as HTMLInputElement).value).toBe("Income");

    const saveButton = within(updatedRow as HTMLElement).getByRole("button", { name: /save/i });
    fireEvent.click(saveButton);

    expect(updateInstrumentMetadata).not.toHaveBeenCalled();

    await waitFor(() =>
      expect(createInstrumentMetadata).toHaveBeenCalledWith(
        "CCC",
        "L",
        expect.objectContaining({ grouping: "Income" }),
      ),
    );
  });
});

