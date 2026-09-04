import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useNavigate } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";

import ReportTemplateCreator from "@/pages/ReportTemplateCreator";

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
  });

  it("opens the report builder in create mode", () => {
    renderPage();

    expect(
      screen.getByTestId("report-builder-heading"),
    ).toHaveTextContent("Create report template");
  });

  it("navigates back to /reports after a successful save (happy path)", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.type(
      screen.getByLabelText(/template name/i),
      "My custom template",
    );

    await user.click(screen.getByRole("button", { name: /create template/i }));

    const navigateSpy = vi.mocked(useNavigate)();
    await vi.waitFor(() => expect(navigateSpy).toHaveBeenCalledWith("/reports"));
  });

  it("shows a validation error and does not navigate away when the name is left blank", async () => {
    const user = userEvent.setup();
    renderPage();

    // Metrics/columns already have sensible defaults selected, so the only
    // missing required field is the template name.
    await user.click(screen.getByRole("button", { name: /create template/i }));

    expect(await screen.findByText("Name is required")).toBeInTheDocument();
    const navigateSpy = vi.mocked(useNavigate)();
    expect(navigateSpy).not.toHaveBeenCalled();
  });

  it("navigates back to /reports when cancelled", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("button", { name: /^close$/i }));

    const navigateSpy = vi.mocked(useNavigate)();
    expect(navigateSpy).toHaveBeenCalledWith("/reports");
  });
});
