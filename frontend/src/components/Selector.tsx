import type {CSSProperties} from "react";

type Option = {
  value: string;
  label: string;
};

type Props = {
  label: string;
  options: Option[];
  value: string;
  onChange: (value: string) => void;
  style?: CSSProperties;
};

export function Selector({label, options, value, onChange, style}: Props) {
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
        onChange={(e) => onChange(e.target.value)}
        style={{marginLeft: "0.5rem"}}
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

export type {Option};
