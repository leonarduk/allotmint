import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useNavigate } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";

import ReportTemplateCreator from "@/pages/ReportTemplateCreator";

const mockCreateTemplate = vi.hoisted(() => vi.fn());

vi.mock("@/api/reports", () => ({
  createReportTemplate: mockCreateTemplate,
}));

function renderPage() {
  return render(
    <MemoryRouter>
      <ReportTemplateCreator />
    </MemoryRouter>,
  );
}

describe("ReportTemplateCreator page", () => {
  beforeEach(() => {
    // react-router-dom's useNavigate is globally mocked to a stable vi.fn()
    // (see src/setupTests.ts, #4810) that is never reset between tests, so
    // clear it explicitly before each render.
    vi.mocked(useNavigate)().mockClear();
    mockCreateTemplate.mockReset();
    mockCreateTemplate.mockImplementation(async (payload) => ({
      ...payload,
      builtin: false,
    }));
  });

  it("opens the report builder in create mode", () => {
    renderPage();

    expect(
      screen.getByTestId("report-builder-heading"),
    ).toHaveTextContent("Create report template");
  });

  it("persists the template via POST and returns to /reports with it (#10914)", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.type(
      screen.getByLabelText(/template name/i),
      "QA temp template",
    );
    // Swap the default performance section for holdings, keeping only
    // Ticker and Value.
    await user.click(screen.getByRole("checkbox", { name: "Performance summary" }));
    await user.click(screen.getByRole("checkbox", { name: "Holdings breakdown" }));
    for (const column of ["Exchange", "Units", "Price"]) {
      await user.click(
        screen.getByRole("checkbox", { name: `Holdings breakdown: ${column}` }),
      );
    }

    await user.click(screen.getByRole("button", { name: /create template/i }));

    const navigateSpy = vi.mocked(useNavigate)();
    await vi.waitFor(() =>
      expect(navigateSpy).toHaveBeenCalledWith("/reports", {
        state: {
          createdTemplate: {
            template_id: "qa-temp-template",
            name: "QA temp template",
          },
        },
      }),
    );
    expect(mockCreateTemplate).toHaveBeenCalledWith({
      template_id: "qa-temp-template",
      name: "QA temp template",
      sections: [
        {
          id: "holdings",
          title: "Holdings breakdown",
          source: "allocation",
          columns: [
            { key: "ticker", label: "Ticker", type: "string" },
            { key: "value", label: "Value", type: "number" },
          ],
        },
      ],
    });
  });

  it("shows the backend error and stays open when the save fails", async () => {
    mockCreateTemplate.mockRejectedValue(
      new Error("Template qa-temp-template already exists"),
    );
    const user = userEvent.setup();
    renderPage();

    await user.type(screen.getByLabelText(/template name/i), "QA temp template");
    await user.click(screen.getByRole("button", { name: /create template/i }));

    expect(
      await screen.findByText("Template qa-temp-template already exists"),
    ).toBeInTheDocument();
    expect(vi.mocked(useNavigate)()).not.toHaveBeenCalled();
  });

  it("shows a validation error and does not navigate away when the name is left blank", async () => {
    const user = userEvent.setup();
    renderPage();

    // Sections/columns already have sensible defaults selected, so the only
    // missing required field is the template name.
    await user.click(screen.getByRole("button", { name: /create template/i }));

    expect(await screen.findByText("Name is required")).toBeInTheDocument();
    const navigateSpy = vi.mocked(useNavigate)();
    expect(navigateSpy).not.toHaveBeenCalled();
    expect(mockCreateTemplate).not.toHaveBeenCalled();
  });

  it("requires at least one column in each chosen section", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.type(screen.getByLabelText(/template name/i), "Empty section");
    for (const column of ["Metric", "Value", "Units"]) {
      await user.click(
        screen.getByRole("checkbox", { name: `Performance summary: ${column}` }),
      );
    }
    await user.click(screen.getByRole("button", { name: /create template/i }));

    expect(
      await screen.findByText("Select at least one column for each section"),
    ).toBeInTheDocument();
    expect(mockCreateTemplate).not.toHaveBeenCalled();
  });

  it("navigates back to /reports when cancelled", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("button", { name: /^close$/i }));

    const navigateSpy = vi.mocked(useNavigate)();
    expect(navigateSpy).toHaveBeenCalledWith("/reports");
    expect(mockCreateTemplate).not.toHaveBeenCalled();
  });
});
