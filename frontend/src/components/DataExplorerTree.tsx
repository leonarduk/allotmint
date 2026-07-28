import { useEffect, useState } from "react";
import { listDataExplorerDirectory } from "../api";
import type { DataExplorerEntry } from "../types";

function formatSize(size: number | null): string {
  if (size === null) return "";
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

interface TreeNodeProps {
  path: string;
  name: string;
  depth: number;
  defaultExpanded?: boolean;
  selectedPath: string | null;
  onSelectFile: (path: string) => void;
}

function TreeNode({
  path,
  name,
  depth,
  defaultExpanded = false,
  selectedPath,
  onSelectFile,
}: TreeNodeProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const [entries, setEntries] = useState<DataExplorerEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!expanded || entries !== null) return;
    let cancelled = false;
    setLoading(true);
    listDataExplorerDirectory(path)
      .then((res) => {
        if (cancelled) return;
        setEntries(res.entries);
        setError(null);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // `loading` is intentionally excluded: it's set inside this effect, and
    // including it re-runs the effect on the very next render (loading
    // false -> true), whose cleanup then marks the in-flight request
    // `cancelled` before it ever resolves.
  }, [expanded, entries, path]);

  return (
    <li style={{ listStyle: "none" }}>
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        style={{
          paddingLeft: `${depth * 1}rem`,
          background: "none",
          border: "none",
          cursor: "pointer",
          fontWeight: "bold",
          textAlign: "left",
          width: "100%",
        }}
      >
        <span aria-hidden="true">{expanded ? "▼" : "▶"} </span>
        {name}
      </button>
      {expanded && (
        <ul style={{ paddingLeft: 0, margin: 0 }}>
          {loading && (
            <li style={{ paddingLeft: `${(depth + 1) * 1}rem` }}>Loading…</li>
          )}
          {error && (
            <li style={{ paddingLeft: `${(depth + 1) * 1}rem`, color: "red" }}>
              {error}
            </li>
          )}
          {entries?.map((entry) =>
            entry.type === "dir" ? (
              <TreeNode
                key={entry.path}
                path={entry.path}
                name={entry.name}
                depth={depth + 1}
                selectedPath={selectedPath}
                onSelectFile={onSelectFile}
              />
            ) : (
              <li key={entry.path} style={{ listStyle: "none" }}>
                <button
                  type="button"
                  onClick={() => onSelectFile(entry.path)}
                  style={{
                    paddingLeft: `${(depth + 1) * 1}rem`,
                    background:
                      selectedPath === entry.path ? "#e0e8ff" : "none",
                    border: "none",
                    cursor: "pointer",
                    textAlign: "left",
                    width: "100%",
                  }}
                >
                  {entry.name}{" "}
                  <span style={{ color: "#888", fontSize: "0.85em" }}>
                    {formatSize(entry.size)}
                  </span>
                </button>
              </li>
            ),
          )}
          {entries !== null && entries.length === 0 && !loading && !error && (
            <li
              style={{ paddingLeft: `${(depth + 1) * 1}rem`, color: "#888" }}
            >
              (empty)
            </li>
          )}
        </ul>
      )}
    </li>
  );
}

interface DataExplorerTreeProps {
  selectedPath: string | null;
  onSelectFile: (path: string) => void;
}

export default function DataExplorerTree({
  selectedPath,
  onSelectFile,
}: DataExplorerTreeProps) {
  return (
    <ul style={{ paddingLeft: 0, margin: 0 }}>
      <TreeNode
        path=""
        name="data"
        depth={0}
        defaultExpanded
        selectedPath={selectedPath}
        onSelectFile={onSelectFile}
      />
    </ul>
  );
}
