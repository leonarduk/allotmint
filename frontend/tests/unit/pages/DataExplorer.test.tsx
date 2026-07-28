import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { act } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mockListDataExplorerDirectory = vi.hoisted(() => vi.fn());
const mockGetDataExplorerFile = vi.hoisted(() => vi.fn());

vi.mock("@/api", async () => {
  const actual = await vi.importActual<typeof import("@/api")>("@/api");
  return {
    ...actual,
    listDataExplorerDirectory: mockListDataExplorerDirectory,
    getDataExplorerFile: mockGetDataExplorerFile,
  };
});

import DataExplorer from "@/pages/DataExplorer";

beforeEach(() => {
  (globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;
  vi.clearAllMocks();
});

describe("DataExplorer page", () => {
  it("lists the root directory and expands a subdirectory", async () => {
    mockListDataExplorerDirectory.mockImplementation((path: string) => {
      if (path === "") {
        return Promise.resolve({
          path: "",
          entries: [
            { name: "timeseries", path: "timeseries", type: "dir", size: null, modified: "2026-01-01T00:00:00Z" },
            { name: "accounts.json", path: "accounts.json", type: "file", size: 42, modified: "2026-01-01T00:00:00Z" },
          ],
        });
      }
      if (path === "timeseries") {
        return Promise.resolve({
          path: "timeseries",
          entries: [
            { name: "meta.json", path: "timeseries/meta.json", type: "file", size: 10, modified: "2026-01-01T00:00:00Z" },
          ],
        });
      }
      return Promise.reject(new Error(`unexpected path ${path}`));
    });

    render(<DataExplorer />);

    expect(await screen.findByText("accounts.json")).toBeInTheDocument();
    expect(await screen.findByText("timeseries")).toBeInTheDocument();
    expect(screen.queryByText("meta.json")).not.toBeInTheDocument();

    await act(async () => {
      await userEvent.click(screen.getByText("timeseries"));
    });

    expect(await screen.findByText("meta.json")).toBeInTheDocument();
  });

  it("previews a selected file's contents", async () => {
    mockListDataExplorerDirectory.mockResolvedValue({
      path: "",
      entries: [
        { name: "notes.txt", path: "notes.txt", type: "file", size: 11, modified: "2026-01-01T00:00:00Z" },
      ],
    });
    mockGetDataExplorerFile.mockResolvedValue({
      path: "notes.txt",
      size: 11,
      modified: "2026-01-01T00:00:00Z",
      truncated: false,
      content: "hello world",
    });

    render(<DataExplorer />);

    const fileButton = await screen.findByText("notes.txt");
    await act(async () => {
      await userEvent.click(fileButton);
    });

    expect(await screen.findByText("hello world")).toBeInTheDocument();
    expect(mockGetDataExplorerFile).toHaveBeenCalledWith("notes.txt");
  });

  it("shows an error when the file preview request fails", async () => {
    mockListDataExplorerDirectory.mockResolvedValue({
      path: "",
      entries: [
        { name: "cache.parquet", path: "cache.parquet", type: "file", size: 99, modified: "2026-01-01T00:00:00Z" },
      ],
    });
    mockGetDataExplorerFile.mockRejectedValue(new Error("File type is not previewable"));

    render(<DataExplorer />);

    const fileButton = await screen.findByText("cache.parquet");
    await act(async () => {
      await userEvent.click(fileButton);
    });

    expect(await screen.findByText("File type is not previewable")).toBeInTheDocument();
  });
});
