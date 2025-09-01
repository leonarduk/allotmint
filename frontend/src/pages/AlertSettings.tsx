import { useEffect, useState } from "react";
import Menu from "../components/Menu";
import { getAlertThreshold, setAlertThreshold } from "../api";

export default function AlertSettings() {
  const [owner, setOwner] = useState("default");
  const [threshold, setThreshold] = useState<number | "">("");
  const [status, setStatus] = useState<"idle" | "saving" | "saved" | "error">(
    "idle",
  );

  useEffect(() => {
    getAlertThreshold(owner)
      .then((r) => setThreshold(r.threshold))
      .catch(() => setThreshold(""));
  }, [owner]);

  async function save() {
    if (threshold === "") return;
    setStatus("saving");
    try {
      await setAlertThreshold(owner, Number(threshold));
      setStatus("saved");
    } catch {
      setStatus("error");
    }
  }

  return (
    <div style={{ maxWidth: 600, margin: "0 auto", padding: "1rem" }}>
      <Menu />
      <h1>Alert Settings</h1>
      <div style={{ marginBottom: "1rem" }}>
        <label>
          Owner: {" "}
          <input value={owner} onChange={(e) => setOwner(e.target.value)} />
        </label>
      </div>
      <div>
        <label>
          Threshold %:{" "}
          <input
            type="number"
            value={threshold}
            onChange={(e) => setThreshold(e.target.value === "" ? "" : Number(e.target.value))}
            style={{ width: "4rem" }}
          />
        </label>
        <button onClick={save} style={{ marginLeft: "0.5rem" }}>
          Save
        </button>
        {status === "saved" && <span style={{ marginLeft: "0.5rem" }}>Saved</span>}
        {status === "error" && <span style={{ marginLeft: "0.5rem" }}>Error</span>}
      </div>
    </div>
  );
}
