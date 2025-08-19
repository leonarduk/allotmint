import { fireEvent, render, screen, within } from "@testing-library/react";
import { vi } from "vitest";

const mockGetConfig = vi.hoisted(() => vi.fn());
const mockUpdateConfig = vi.hoisted(() => vi.fn());

vi.mock("../api", () => ({
  API_BASE: "",
  getConfig: mockGetConfig,
  updateConfig: mockUpdateConfig,
}));

import Support from "./Support";

beforeEach(() => {
  vi.clearAllMocks();
  mockGetConfig.mockResolvedValue({
    flag: true,
    theme: "system",
    tabs: { group: true, owner: true, instrument: true, support: true },
  });
});

describe("Support page", () => {
  it("renders environment heading", () => {
    render(<Support />);
    expect(screen.getByText(/Environment/)).toBeInTheDocument();
  });

  it("shows swagger link for VITE_API_URL", () => {
    vi.stubEnv("VITE_API_URL", "http://localhost:8000");
    render(<Support />);
    expect(
      screen.getByRole("link", { name: "http://localhost:8000" })
    ).toHaveAttribute("href", "http://localhost:8000");
    expect(screen.getByRole("link", { name: "swagger" })).toHaveAttribute(
      "href",
      "http://localhost:8000/docs#/"
    );
    vi.unstubAllEnvs();
  });

  it("stringifies fresh config after saving", async () => {
  mockGetConfig.mockResolvedValueOnce({
    flag: true,
    theme: "system",
    tabs: { group: true, owner: true, instrument: true, support: true },
  });
  mockGetConfig.mockResolvedValueOnce({
    flag: false,
    count: 5,
    theme: "dark",
    tabs: { group: true, owner: true, instrument: false, support: true },
  });
    mockUpdateConfig.mockResolvedValue(undefined);

    render(<Support />);

    const saveButton = await screen.findByRole("button", { name: "Save" });
    fireEvent.click(saveButton);

    await screen.findByDisplayValue("5");

    const flagToggle = screen.getByRole("checkbox", { name: /flag/i });
    expect(flagToggle).not.toBeChecked();
    expect(screen.getByDisplayValue("5")).toBeInTheDocument();
  });

  it("renders tab toggles and allows toggling", async () => {
    render(<Support />);
    await screen.findByText(/Tabs Enabled/i);
    const instrument = await screen.findByRole("checkbox", {
      name: /instrument/i,
    });
    const support = screen.getByRole("checkbox", { name: /support/i });
    expect(instrument).toBeChecked();
    expect(support).toBeChecked();
    fireEvent.click(instrument);
    fireEvent.click(support);
    expect(instrument).not.toBeChecked();
    expect(support).not.toBeChecked();
  });

  it("separates switches from other parameters", async () => {
    render(<Support />);
    const switchesHeading = await screen.findByRole("heading", {
      name: /Other Switches/i,
    });
    const switchesSection = switchesHeading.parentElement as HTMLElement;
    expect(
      within(switchesSection).getByRole("checkbox", { name: /flag/i })
    ).toBeInTheDocument();
    expect(
      within(switchesSection).queryByRole("radio", { name: /dark/i })
    ).toBeNull();

    const paramsHeading = screen.getByRole("heading", {
      name: /Other parameters/i,
    });
    const paramsSection = paramsHeading.parentElement as HTMLElement;
    expect(
      within(paramsSection).getByRole("radio", { name: /dark/i })
    ).toBeInTheDocument();
    expect(
      within(paramsSection).queryByRole("checkbox", { name: /flag/i })
    ).toBeNull();
  });

  it("allows selecting theme via radio buttons", async () => {
    render(<Support />);
    const dark = await screen.findByRole("radio", { name: "dark" });
    const light = screen.getByRole("radio", { name: "light" });
    fireEvent.click(light);
    expect(light).toBeChecked();
    fireEvent.click(dark);
    expect(dark).toBeChecked();
  });
});

