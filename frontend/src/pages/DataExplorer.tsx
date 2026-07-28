import { useState } from "react";
import { useTranslation } from "react-i18next";
import { getDataExplorerFile } from "../api";
import DataExplorerTree from "../components/DataExplorerTree";
import type { DataExplorerFile } from "../types";

export default function DataExplorer() {
  const { t } = useTranslation();
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [file, setFile] = useState<DataExplorerFile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSelectFile = (path: string) => {
    setSelectedPath(path);
    setFile(null);
    setError(null);
    setLoading(true);
    getDataExplorerFile(path)
      .then((res) => setFile(res))
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  };

  return (
    <div className="container mx-auto p-4 max-w-6xl">
      <h2 className="mb-4 text-xl md:text-2xl">
        {t("app.modes.dataexplorer")}
      </h2>
      <div style={{ display: "flex", gap: "1rem", alignItems: "flex-start" }}>
        <div
          style={{
            width: "35%",
            minWidth: "250px",
            border: "1px solid #ddd",
            borderRadius: "4px",
            padding: "0.5rem",
            maxHeight: "70vh",
            overflow: "auto",
          }}
        >
          <DataExplorerTree
            selectedPath={selectedPath}
            onSelectFile={handleSelectFile}
          />
        </div>
        <div
          style={{
            flex: 1,
            border: "1px solid #ddd",
            borderRadius: "4px",
            padding: "0.5rem",
            minHeight: "10rem",
          }}
        >
          {!selectedPath && <p>Select a file to preview its contents.</p>}
          {loading && <p>{t("common.loading")}</p>}
          {error && <p style={{ color: "red" }}>{error}</p>}
          {file && (
            <div>
              <p>
                <strong>{file.path}</strong> — {file.size} bytes — last
                modified {file.modified}
              </p>
              {file.truncated && (
                <p style={{ color: "#a66" }}>
                  Preview truncated; showing only the first part of the file.
                </p>
              )}
              <pre
                style={{
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-word",
                  maxHeight: "60vh",
                  overflow: "auto",
                }}
              >
                {file.content}
              </pre>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
