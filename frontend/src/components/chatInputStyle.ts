import type { CSSProperties } from "react";

// Tailwind's preflight strips native input borders, and in the light theme the
// controls' white background matches --drawer-bg, so an unstyled input in the
// chat panel cannot be seen at all (#9048). Every text field in the chat uses this.
export const CHAT_INPUT_STYLE: CSSProperties = {
  border: "1px solid var(--input-border)",
  borderRadius: "4px",
  padding: "0.4rem 0.5rem",
  boxSizing: "border-box",
  font: "inherit",
};
