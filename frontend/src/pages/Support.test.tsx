import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";

const mockGetConfig = vi.fn();
const mockUpdateConfig = vi.fn();

vi.mock("../api", () => ({
  API_BASE: "",
  getConfig: mockGetConfig,
  updateConfig: mockUpdateConfig,
}));

import Support from "./Support";

beforeEach(() => {
  vi.clearAllMocks();
  mockGetConfig.mockResolvedValue({ flag: true });
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
    mockGetConfig.mockResolvedValueOnce({ flag: true });
    mockGetConfig.mockResolvedValueOnce({ flag: false, count: 5 });
    mockUpdateConfig.mockResolvedValue(undefined);

    render(<Support />);

    const saveButton = await screen.findByRole("button", { name: "Save" });
    fireEvent.click(saveButton);

    await screen.findByDisplayValue("5");

    expect(screen.getByDisplayValue("false")).toBeInTheDocument();
    expect(screen.getByDisplayValue("5")).toBeInTheDocument();
  });
});

