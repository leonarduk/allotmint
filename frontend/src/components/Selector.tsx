import { memo } from "react";
import type { CSSProperties, ChangeEventHandler } from "react";

type Option = {
  value: string;
  label: string;
};

type Props = {
  label: string;
  options: Option[];
  value: string;
  onChange: ChangeEventHandler<HTMLSelectElement>;
  style?: CSSProperties;
};

function SelectorComponent({ label, options, value, onChange, style }: Props) {
  return (
    <label
      style={{
        display: "inline-block",
        marginRight: "0.5rem",
        marginBottom: "1rem",
        ...style,
      }}
    >
      {label}:
      <select
        value={value}
        onChange={onChange}
        style={{ marginLeft: "0.5rem" }}
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}

export const Selector = memo(SelectorComponent);

export type { Option };
