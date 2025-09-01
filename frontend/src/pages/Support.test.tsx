import { render, screen, within, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";

const mockGetConfig = vi.hoisted(() => vi.fn());
const mockUpdateConfig = vi.hoisted(() => vi.fn());
const mockGetOwners = vi.hoisted(() => vi.fn());
const mockSavePushSubscription = vi.hoisted(() => vi.fn());
const mockDeletePushSubscription = vi.hoisted(() => vi.fn());

vi.mock("../api", () => ({
  API_BASE: "",
  getConfig: mockGetConfig,
  updateConfig: mockUpdateConfig,
  getOwners: mockGetOwners,
  savePushSubscription: mockSavePushSubscription,
  deletePushSubscription: mockDeletePushSubscription,
}));

import Support from "./Support";

beforeEach(() => {
  (globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;
  vi.clearAllMocks();
  mockGetConfig.mockResolvedValue({
    flag: true,
    theme: "system",
    tabs: {
      group: true,
      owner: true,
      instrument: true,
      trading: true,
      support: true,
      reports: true,
    },
  });
  mockGetOwners.mockResolvedValue([{ owner: "alex", accounts: [] }]);
});

describe("Support page", () => {
  it("renders environment heading", async () => {
    render(<Support />, { wrapper: MemoryRouter });
    expect(await screen.findByText(/Environment/)).toBeInTheDocument();
  });

  it("shows owner selector", async () => {
    render(<Support />, { wrapper: MemoryRouter });
    expect(await screen.findByLabelText(/Owner/i)).toBeInTheDocument();
  });

  it("handles owner fetch failure gracefully", async () => {
    mockGetOwners.mockRejectedValueOnce(new Error("fail"));
    render(<Support />, { wrapper: MemoryRouter });
    const select = await screen.findByLabelText(/Owner/i);
    expect((select as HTMLSelectElement).options.length).toBe(0);
  });

  it("shows swagger link for VITE_API_URL", async () => {
    vi.stubEnv("VITE_API_URL", "http://localhost:8000");
    render(<Support />, { wrapper: MemoryRouter });
    expect(
      await screen.findByRole("link", { name: "http://localhost:8000" })
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
    tabs: {
      group: true,
      owner: true,
      instrument: true,
      trading: true,
      support: true,
      reports: true,
    },
  });
  mockGetConfig.mockResolvedValueOnce({
    flag: false,
    count: 5,
    theme: "dark",
    tabs: {
      group: true,
      owner: true,
      instrument: false,
      trading: true,
      support: true,
      reports: true,
    },
  });
    mockUpdateConfig.mockResolvedValue(undefined);

    render(<Support />, { wrapper: MemoryRouter });

    const saveButton = await screen.findByRole("button", { name: "Save" });
    await act(async () => {
      await userEvent.click(saveButton);
    });

    await screen.findByDisplayValue("5");

    const flagToggle = screen.getByRole("checkbox", { name: /flag/i });
    expect(flagToggle).not.toBeChecked();
    expect(screen.getByDisplayValue("5")).toBeInTheDocument();
  });

  it("renders tab toggles and allows toggling", async () => {
    render(<Support />, { wrapper: MemoryRouter });
    await screen.findByText(/Tabs Enabled/i);
    const instrument = await screen.findByRole("checkbox", {
      name: /instrument/i,
    });
    const support = screen.getByRole("checkbox", { name: /support/i });
    expect(instrument).toBeChecked();
    expect(support).toBeChecked();
    await act(async () => {
      await userEvent.click(instrument);
    });
    await act(async () => {
      await userEvent.click(support);
    });
    expect(instrument).not.toBeChecked();
    expect(support).not.toBeChecked();
  });

  it("separates switches from other parameters", async () => {
    render(<Support />, { wrapper: MemoryRouter });
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
    render(<Support />, { wrapper: MemoryRouter });
    const dark = await screen.findByRole("radio", { name: "dark" });
    const light = screen.getByRole("radio", { name: "light" });
    await act(async () => {
      await userEvent.click(light);
    });
    expect(light).toBeChecked();
    await act(async () => {
      await userEvent.click(dark);
    });
    expect(dark).toBeChecked();
  });
});

