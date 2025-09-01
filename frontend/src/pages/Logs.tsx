import { useEffect, useState } from "react";
import { API_BASE } from "../api";

export default function Logs() {
  const [text, setText] = useState("");

  useEffect(() => {
    fetch(`${API_BASE}/logs`)
      .then((res) => (res.ok ? res.text() : ""))
      .then(setText)
      .catch(() => setText(""));
  }, []);

  return <pre style={{ whiteSpace: "pre-wrap" }}>{text}</pre>;
}
