import { fireEvent, render, screen } from "@testing-library/react";
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
    tabs: { instrument: true, support: true },
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
      tabs: { instrument: true, support: true },
    });
    mockGetConfig.mockResolvedValueOnce({
      flag: false,
      count: 5,
      theme: "dark",
      tabs: { instrument: false, support: true },
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
    await screen.findByText(/Feature Switches/i);
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

