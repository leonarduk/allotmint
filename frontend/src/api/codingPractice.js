import { API_BASE } from "../api";

async function fetchJson(url, init) {
  const res = await fetch(url, init);
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}`);
  }
  return res.json();
}

export const getPuzzles = () => fetchJson(`${API_BASE}/codingpractice`);

export const createPuzzle = (puzzle) =>
  fetchJson(`${API_BASE}/codingpractice`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(puzzle),
  });

export const updatePuzzle = (id, puzzle) =>
  fetchJson(`${API_BASE}/codingpractice/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(puzzle),
  });

export const deletePuzzle = (id) =>
  fetchJson(`${API_BASE}/codingpractice/${id}`, { method: "DELETE" });
