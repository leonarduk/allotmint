import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { CsvImportForm } from "@/components/CsvImportForm";
import { importHoldingsCsv } from "@/api";

vi.mock("@/api", () => ({
  importHoldingsCsv: vi.fn(),
}));

describe("CsvImportForm", () => {
  beforeEach(() => {
    vi.mocked(importHoldingsCsv).mockReset();
  });

  const csvFile = new File(["a,b\n1,2"], "holdings.csv", { type: "text/csv" });

  it("disables submit until a provider and file are chosen", async () => {
    render(<CsvImportForm owner="alice" accountTypes={["ISA", "SIPP"]} />);

    const submit = screen.getByRole("button", { name: "Import" });
    expect(submit).toBeDisabled();

    await userEvent.selectOptions(screen.getByLabelText("Provider"), "degiro");
    expect(submit).toBeDisabled();

    const fileInput = screen.getByLabelText("CSV file");
    await userEvent.upload(fileInput, csvFile);
    expect(submit).toBeEnabled();
  });

  it("submits the selected account, provider and file as multipart data", async () => {
    vi.mocked(importHoldingsCsv).mockResolvedValue({
      path: "/data/accounts/alice/ISA.json",
    });

    render(<CsvImportForm owner="alice" accountTypes={["ISA", "SIPP"]} />);

    await userEvent.selectOptions(screen.getByLabelText("Account"), "SIPP");
    await userEvent.selectOptions(screen.getByLabelText("Provider"), "hargreaves");
    await userEvent.upload(screen.getByLabelText("CSV file"), csvFile);
    await userEvent.click(screen.getByRole("button", { name: "Import" }));

    expect(importHoldingsCsv).toHaveBeenCalledWith(
      "alice",
      "SIPP",
      "hargreaves",
      csvFile,
    );
    expect(
      await screen.findByText(/Imported successfully/),
    ).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(
      "/data/accounts/alice/ISA.json",
    );
  });

  it("shows the backend error message for an unknown provider", async () => {
    vi.mocked(importHoldingsCsv).mockRejectedValue(
      new Error("Unknown provider: bogus"),
    );

    render(<CsvImportForm owner="alice" accountTypes={["ISA"]} />);

    await userEvent.selectOptions(screen.getByLabelText("Provider"), "degiro");
    await userEvent.upload(screen.getByLabelText("CSV file"), csvFile);
    await userEvent.click(screen.getByRole("button", { name: "Import" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Unknown provider: bogus",
    );
  });
});
