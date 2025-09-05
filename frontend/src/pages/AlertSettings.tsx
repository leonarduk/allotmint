import { useEffect, useState } from "react";
import Menu from "../components/Menu";
import { getAlertThreshold, setAlertThreshold } from "../api";
import { useUser } from "../UserContext";

export default function AlertSettings() {
  const { profile } = useUser();
  const owner = profile?.email;
  const [threshold, setThreshold] = useState<number | "">("");
  const [status, setStatus] = useState<"idle" | "saving" | "saved" | "error">(
    "idle",
  );

  useEffect(() => {
    if (!owner) {
      setThreshold("");
      return;
    }
    getAlertThreshold(owner)
      .then((r) => setThreshold(r.threshold))
      .catch(() => setThreshold(""));
  }, [owner]);

  async function save() {
    if (threshold === "" || !owner) return;
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
      <div>
        <label>
          Threshold %:{" "}
          <input
            type="number"
            value={threshold}
            onChange={(e) =>
              setThreshold(e.target.value === "" ? "" : Number(e.target.value))
            }
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
