import { useState, useEffect } from "react";
import { getPuzzles, createPuzzle, updatePuzzle, deletePuzzle } from "./api/codingPractice";

export default function CodingPracticePage() {
  const [puzzles, setPuzzles] = useState([]);
  const [form, setForm] = useState({ title: "", description: "" });
  const [editing, setEditing] = useState(null);

  const load = async () => {
    try {
      const data = await getPuzzles();
      setPuzzles(data);
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (editing) {
      await updatePuzzle(editing, form);
    } else {
      await createPuzzle(form);
    }
    setForm({ title: "", description: "" });
    setEditing(null);
    load();
  };

  const startEdit = (p) => {
    setEditing(p.id);
    setForm({ title: p.title, description: p.description });
  };

  const handleDelete = async (id) => {
    await deletePuzzle(id);
    load();
  };

  return (
    <div>
      <h2>Coding Practice</h2>
      <form onSubmit={handleSubmit}>
        <input
          placeholder="Title"
          value={form.title}
          onChange={(e) => setForm({ ...form, title: e.target.value })}
        />
        <input
          placeholder="Description"
          value={form.description}
          onChange={(e) => setForm({ ...form, description: e.target.value })}
        />
        <button type="submit">{editing ? "Update" : "Add"}</button>
      </form>
      <ul>
        {puzzles.map((p) => (
          <li key={p.id}>
            <strong>{p.title}</strong> - {p.description}{" "}
            <button onClick={() => startEdit(p)}>Edit</button>{" "}
            <button onClick={() => handleDelete(p.id)}>Delete</button>
          </li>
        ))}
      </ul>
    </div>
  );
}
