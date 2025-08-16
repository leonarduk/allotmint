import { describe, it, expect, beforeEach, vi } from "vitest";
import {
  getPuzzles,
  createPuzzle,
  updatePuzzle,
  deletePuzzle,
} from "./codingPractice.js";
import { API_BASE } from "../api";

describe("coding practice api", () => {
  beforeEach(() => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve([]),
    });
  });

  it("fetches puzzles", async () => {
    await getPuzzles();
    expect(fetch).toHaveBeenCalledWith(`${API_BASE}/codingpractice`, undefined);
  });

  it("creates puzzle", async () => {
    await createPuzzle({ title: "x" });
    expect(fetch).toHaveBeenCalledWith(`${API_BASE}/codingpractice`, expect.objectContaining({ method: "POST" }));
  });

  it("updates puzzle", async () => {
    await updatePuzzle("1", { title: "y" });
    expect(fetch).toHaveBeenCalledWith(`${API_BASE}/codingpractice/1`, expect.objectContaining({ method: "PUT" }));
  });

  it("deletes puzzle", async () => {
    await deletePuzzle("1");
    expect(fetch).toHaveBeenCalledWith(`${API_BASE}/codingpractice/1`, expect.objectContaining({ method: "DELETE" }));
  });
});
