import {API_BASE, fetchJson} from "../api";

export const getPuzzles = () => fetchJson(`${API_BASE}/codingpractice`);

export const createPuzzle = (puzzle) =>
  fetchJson(`${API_BASE}/codingpractice`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(puzzle),
  });

export const updatePuzzle = (id, puzzle) =>
  fetchJson(`${API_BASE}/codingpractice/${id}`, {
    method: "PUT",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(puzzle),
  });

export const deletePuzzle = (id) =>
  fetchJson(`${API_BASE}/codingpractice/${id}`, {method: "DELETE"});
