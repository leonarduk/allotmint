import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import ValueAtRisk from "./ValueAtRisk";

describe("ValueAtRisk component", () => {
  test("renders VaR value and selectors", async () => {
    render(<ValueAtRisk value={123.45} days={10} confidence={0.95} />);

    expect(screen.getByText("123.45")).toBeInTheDocument();
    const periodSel = screen.getByLabelText(/period/i);
    const confSel = screen.getByLabelText(/confidence/i);
    expect(periodSel).toBeInTheDocument();
    expect(confSel).toBeInTheDocument();

    await userEvent.selectOptions(periodSel, "30");
    await userEvent.selectOptions(confSel, "0.99");
  });
});
