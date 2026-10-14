import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, it, expect, vi } from "vitest";

import i18n from "@/i18n";

vi.mock("@/api", () => ({
  listInstrumentMetadataScan: vi.fn().mockResolvedValue({ warming: false, data: [
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
  ] }),
  createInstrumentMetadata: vi.fn().mockResolvedValue({}),
  updateInstrumentMetadata: vi.fn().mockResolvedValue({}),
  getFundUpkeepProposals: vi.fn().mockResolvedValue([]),
  decideFundUpkeepProposal: vi.fn().mockResolvedValue({}),
}));

import InstrumentAdmin, { INSTRUMENT_ADMIN_PAGE_SIZE } from "@/pages/InstrumentAdmin";
import {
  createInstrumentMetadata,
  listInstrumentMetadataScan,
  updateInstrumentMetadata,
} from "@/api";

describe("InstrumentAdmin page", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

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
    // Neither region field is touched when only the grouping changed.
    const payload = vi.mocked(updateInstrumentMetadata).mock.calls[0][2];
    expect(payload).not.toHaveProperty("region");
    expect(payload).not.toHaveProperty("exposure_region");
  });

  it("shows the effective region and saves an edit as the exposure-region override", async () => {
    vi.mocked(listInstrumentMetadataScan).mockResolvedValueOnce({ warming: false, data: [
      { ticker: "USSC.L", name: "SPDR MSCI USA Small Cap", region: "UK", effective_region: "US" },
      { ticker: "ABC.L", name: "Abc", region: "UK", exposure_region: "Europe", effective_region: "Europe" },
    ] as any });
    render(
      <MemoryRouter>
        <InstrumentAdmin />
      </MemoryRouter>,
    );
    expect(await screen.findByDisplayValue("USSC")).toBeInTheDocument();
    // Rows sort by ticker: ABC first, then USSC.
    const [abcRegion, usscRegion] = screen.getAllByRole("textbox", { name: "Region" });
    // No override: blank, with the derived region as the hint.
    expect(usscRegion).toHaveValue("");
    expect(usscRegion).toHaveAttribute("placeholder", "US");
    expect(abcRegion).toHaveValue("Europe");

    fireEvent.change(usscRegion, { target: { value: "North America" } });
    fireEvent.click(within(usscRegion.closest("tr")!).getByRole("button", { name: /save/i }));
    await waitFor(() =>
      expect(updateInstrumentMetadata).toHaveBeenCalledWith(
        "USSC",
        "L",
        expect.objectContaining({ exposure_region: "North America" }),
      ),
    );
    expect(vi.mocked(updateInstrumentMetadata).mock.calls[0][2]).not.toHaveProperty("region");
  });

  it("does not resend an unchanged exposure-region override", async () => {
    vi.mocked(listInstrumentMetadataScan).mockResolvedValueOnce({ warming: false, data: [
      { ticker: "ABC.L", name: "Abc", region: "UK", exposure_region: "Europe", effective_region: "Europe" },
    ] as any });
    render(
      <MemoryRouter>
        <InstrumentAdmin />
      </MemoryRouter>,
    );
    fireEvent.change(await screen.findByDisplayValue("Abc"), { target: { value: "Abc plc" } });
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() =>
      expect(updateInstrumentMetadata).toHaveBeenCalledWith(
        "ABC",
        "L",
        expect.objectContaining({ name: "Abc plc" }),
      ),
    );
    expect(vi.mocked(updateInstrumentMetadata).mock.calls[0][2]).not.toHaveProperty("exposure_region");
  });

  it("clears the exposure-region override when the region is blanked", async () => {
    vi.mocked(listInstrumentMetadataScan).mockResolvedValueOnce({ warming: false, data: [
      { ticker: "ABC.L", name: "Abc", region: "UK", exposure_region: "Europe", effective_region: "Europe" },
    ] as any });
    render(
      <MemoryRouter>
        <InstrumentAdmin />
      </MemoryRouter>,
    );
    fireEvent.change(await screen.findByDisplayValue("Europe"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() =>
      expect(updateInstrumentMetadata).toHaveBeenCalledWith(
        "ABC",
        "L",
        expect.objectContaining({ exposure_region: null }),
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

    await waitFor(() =>
      expect(createInstrumentMetadata).toHaveBeenCalledWith(
        "CCC",
        "L",
        expect.objectContaining({ grouping: "Income", exposure_region: "UK" }),
      ),
    );

    expect(updateInstrumentMetadata).not.toHaveBeenCalled();
  });

  it("keeps a new row pinned to the top while its ticker is typed", async () => {
    render(
      <MemoryRouter>
        <InstrumentAdmin />
      </MemoryRouter>,
    );
    expect(await screen.findByDisplayValue("AAA")).toBeInTheDocument();

    // An active search must not hide the blank row being added.
    fireEvent.change(
      screen.getByPlaceholderText(i18n.t("instrumentadmin.searchPlaceholder")),
      { target: { value: "alpha" } },
    );
    fireEvent.click(screen.getByRole("button", { name: /add instrument/i }));

    const firstDataRow = () => screen.getAllByRole("row")[1];
    const tickerInput = within(firstDataRow()).getAllByRole("textbox")[0];
    expect((tickerInput as HTMLInputElement).value).toBe("");

    // "ZZZ" sorts after every existing ticker; the row must not move there
    // and its input element must survive (otherwise focus is lost mid-typing).
    fireEvent.change(tickerInput, { target: { value: "ZZZ" } });
    expect(within(firstDataRow()).getAllByRole("textbox")[0]).toBe(tickerInput);
    expect((tickerInput as HTMLInputElement).value).toBe("ZZZ");
  });

  it("shows the server error when saving fails", async () => {
    vi.mocked(createInstrumentMetadata).mockRejectedValueOnce(
      new Error("Instrument already exists"),
    );
    render(
      <MemoryRouter>
        <InstrumentAdmin />
      </MemoryRouter>,
    );
    expect(await screen.findByDisplayValue("AAA")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /add instrument/i }));
    const [tickerInput, exchangeInput, nameInput] = within(
      screen.getAllByRole("row")[1],
    ).getAllByRole("textbox");
    fireEvent.change(tickerInput, { target: { value: "AAA" } });
    fireEvent.change(exchangeInput, { target: { value: "L" } });
    fireEvent.change(nameInput, { target: { value: "Dup" } });
    fireEvent.click(
      within(screen.getAllByRole("row")[1]).getByRole("button", { name: /save/i }),
    );
    expect(await screen.findByText(/Instrument already exists/)).toBeInTheDocument();
  });

  it("renders duplicate symbols without duplicate-key errors and keeps rows independent", async () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    vi.mocked(listInstrumentMetadataScan).mockResolvedValueOnce({
      warming: false,
      data: [
        { ticker: "CASH.GBP", name: "Cash GBP", region: "UK", sector: "Cash", grouping: "ISA" },
        { ticker: "CASH.EUR", name: "Cash EUR", region: "EU", sector: "Cash", grouping: "GIA" },
        { ticker: "CASH.USD", name: "Cash USD", region: "US", sector: "Cash", grouping: "ISA" },
        { ticker: "PFE.L", name: "Pfizer L", region: "UK", sector: "Pharma", grouping: "ISA" },
        { ticker: "PFE.N", name: "Pfizer N", region: "US", sector: "Pharma", grouping: "GIA" },
      ],
    });

    render(
      <MemoryRouter>
        <InstrumentAdmin />
      </MemoryRouter>,
    );

    expect(await screen.findAllByDisplayValue("CASH")).toHaveLength(3);
    expect(screen.getAllByDisplayValue("PFE")).toHaveLength(2);

    const duplicateKeyErrors = consoleError.mock.calls.filter((call) =>
      String(call[0]).includes("Encountered two children with the same key"),
    );
    expect(duplicateKeyErrors).toHaveLength(0);

    fireEvent.change(screen.getByDisplayValue("Cash GBP"), {
      target: { value: "Cash GBP edited" },
    });

    expect(screen.getByDisplayValue("Cash GBP edited")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Cash EUR")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Cash USD")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Pfizer L")).toBeInTheDocument();

    consoleError.mockRestore();
  });
});

describe("InstrumentAdmin while the backend warms its caches (#10754)", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  it("shows the partial list with a notice, fills in on re-poll and keeps unsaved edits", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.mocked(listInstrumentMetadataScan)
      .mockResolvedValueOnce({ warming: true, data: [{ ticker: "AAA.L", name: "Alpha", grouping: "ISA" }] as any })
      .mockResolvedValueOnce({
        warming: false,
        data: [
          { ticker: "AAA.L", name: "Alpha", grouping: "ISA" },
          { ticker: "BBB.N", name: "Beta", grouping: "GIA" },
        ] as any,
      });

    render(
      <MemoryRouter>
        <InstrumentAdmin />
      </MemoryRouter>,
    );

    expect(await screen.findByTestId("admin-warming-notice")).toHaveTextContent("1");
    fireEvent.change(screen.getByDisplayValue("ISA"), { target: { value: "ISA edited" } });

    await vi.advanceTimersByTimeAsync(3_000);

    expect(await screen.findByDisplayValue("BBB")).toBeInTheDocument();
    expect(screen.getByDisplayValue("ISA edited")).toBeInTheDocument();
    expect(screen.queryByTestId("admin-warming-notice")).not.toBeInTheDocument();
  });
});

describe("InstrumentAdmin saving while the backend warms its caches (#10754)", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("keeps the saved row and other unsaved edits when the refreshed list is partial", async () => {
    vi.mocked(listInstrumentMetadataScan)
      .mockResolvedValueOnce({
        warming: false,
        data: [
          { ticker: "AAA.L", name: "Alpha", grouping: "ISA" },
          { ticker: "BBB.N", name: "Beta", grouping: "GIA" },
        ] as any,
      })
      // AAA.L's file changed on save, so the warming cache does not list it yet.
      .mockResolvedValueOnce({ warming: true, data: [{ ticker: "BBB.N", name: "Beta", grouping: "GIA" }] as any })
      .mockResolvedValue({
        warming: false,
        data: [
          { ticker: "AAA.L", name: "Alpha", grouping: "ISA+" },
          { ticker: "BBB.N", name: "Beta", grouping: "GIA" },
        ] as any,
      });

    render(
      <MemoryRouter>
        <InstrumentAdmin />
      </MemoryRouter>,
    );
    expect(await screen.findByDisplayValue("AAA")).toBeInTheDocument();
    fireEvent.change(screen.getByDisplayValue("ISA"), { target: { value: "ISA+" } });
    fireEvent.change(screen.getByDisplayValue("GIA"), { target: { value: "GIA unsaved" } });

    fireEvent.click(screen.getAllByRole("button", { name: /save/i })[0]);

    expect(await screen.findByTestId("admin-warming-notice")).toBeInTheDocument();
    expect(screen.getByDisplayValue("AAA")).toBeInTheDocument();
    expect(screen.getByDisplayValue("ISA+")).toBeInTheDocument();
    expect(screen.getByDisplayValue("GIA unsaved")).toBeInTheDocument();
  });
});

describe("InstrumentAdmin with a large catalogue (#10884)", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  const LARGE_COUNT = 1_200;
  // Zero-padded so ticker order matches numeric order: T0000 … T1199.
  const largeCatalogue = Array.from({ length: LARGE_COUNT }, (_, i) => {
    const n = String(i).padStart(4, "0");
    return { ticker: `T${n}.L`, name: `Instrument ${n}`, region: "UK", grouping: "ISA" };
  });

  const renderLarge = async () => {
    vi.mocked(listInstrumentMetadataScan).mockResolvedValueOnce({
      warming: false,
      data: largeCatalogue as any,
    });
    render(
      <MemoryRouter>
        <InstrumentAdmin />
      </MemoryRouter>,
    );
    expect(await screen.findByDisplayValue("T0000")).toBeInTheDocument();
  };

  const tableInputCount = () => within(screen.getByRole("table")).getAllByRole("textbox").length;

  it("renders only one page of editable rows", async () => {
    await renderLarge();
    // Header row plus one page of data rows, six inputs each.
    expect(screen.getAllByRole("row")).toHaveLength(INSTRUMENT_ADMIN_PAGE_SIZE + 1);
    expect(tableInputCount()).toBe(INSTRUMENT_ADMIN_PAGE_SIZE * 6);
    expect(screen.queryByDisplayValue("T0050")).not.toBeInTheDocument();
    expect(
      screen.getByText(`Page 1 of 24 (instruments 1–50 of ${LARGE_COUNT})`),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Next page" }));
    expect(screen.getByDisplayValue("T0050")).toBeInTheDocument();
    expect(screen.queryByDisplayValue("T0000")).not.toBeInTheDocument();
    expect(tableInputCount()).toBe(INSTRUMENT_ADMIN_PAGE_SIZE * 6);
  });

  it("finds an instrument on a later page by ticker or name", async () => {
    await renderLarge();
    const search = screen.getByPlaceholderText(i18n.t("instrumentadmin.searchPlaceholder"));

    fireEvent.change(search, { target: { value: "t1187" } });
    expect(screen.getAllByRole("row")).toHaveLength(2);
    expect(screen.getByDisplayValue("T1187")).toBeInTheDocument();
    // A single page of matches needs no pager.
    expect(screen.queryByRole("button", { name: "Next page" })).not.toBeInTheDocument();

    fireEvent.change(search, { target: { value: "Instrument 0999" } });
    expect(screen.getAllByRole("row")).toHaveLength(2);
    expect(screen.getByDisplayValue("T0999")).toBeInTheDocument();
  });

  it("returns to the first page when the filter changes", async () => {
    await renderLarge();
    fireEvent.click(screen.getByRole("button", { name: "Next page" }));
    fireEvent.click(screen.getByRole("button", { name: "Next page" }));
    expect(screen.getByDisplayValue("T0100")).toBeInTheDocument();

    // "T00" matches T0000–T0099: two pages, shown from the first.
    fireEvent.change(
      screen.getByPlaceholderText(i18n.t("instrumentadmin.searchPlaceholder")),
      { target: { value: "T00" } },
    );
    expect(screen.getByDisplayValue("T0000")).toBeInTheDocument();
    expect(screen.getByText("Page 1 of 2 (instruments 1–50 of 100)")).toBeInTheDocument();
  });

  it("saves the right instrument from a later page, and a ticker edit keeps the row in place", async () => {
    await renderLarge();
    fireEvent.click(screen.getByRole("button", { name: "Next page" }));
    const row = screen.getByDisplayValue("T0077").closest("tr") as HTMLElement;
    const [tickerInput] = within(row).getAllByRole("textbox");

    // "ZZZ" would sort to the last page; the row must stay where it is.
    fireEvent.change(tickerInput, { target: { value: "ZZZ" } });
    expect(screen.getByDisplayValue("ZZZ")).toBe(tickerInput);
    fireEvent.click(within(row).getByRole("button", { name: /save/i }));

    await waitFor(() =>
      expect(updateInstrumentMetadata).toHaveBeenCalledWith(
        "ZZZ",
        "L",
        expect.objectContaining({ name: "Instrument 0077" }),
      ),
    );
  });

  it("shows a new row on the first page when added from a later page", async () => {
    await renderLarge();
    fireEvent.click(screen.getByRole("button", { name: "Next page" }));
    fireEvent.click(screen.getByRole("button", { name: /add instrument/i }));
    const [tickerInput] = within(screen.getAllByRole("row")[1]).getAllByRole("textbox");
    expect(tickerInput).toHaveValue("");
    expect(screen.getByDisplayValue("T0000")).toBeInTheDocument();
  });
});
