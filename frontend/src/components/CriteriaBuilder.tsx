export interface Criterion {
  field: string;
  operator: string;
  value: string;
}

interface CriteriaBuilderProps {
  criteria: Criterion[];
  onChange: (criteria: Criterion[]) => void;
}

const FIELDS = ["peg_ratio", "pe_ratio"];
const OPERATORS = [">", "<"];

/**
 * Very small criteria builder used by tests. It supports adding, editing and
 * removing criteria. Each change will emit the full criteria array via
 * `onChange`.
 */
export function CriteriaBuilder({ criteria, onChange }: CriteriaBuilderProps) {
  function update(index: number, updates: Partial<Criterion>) {
    const updated = [...criteria];
    updated[index] = { ...updated[index], ...updates };
    onChange(updated);
  }

  function add() {
    onChange([...criteria, { field: "", operator: "", value: "" }]);
  }

  function remove(index: number) {
    onChange(criteria.filter((_, i) => i !== index));
  }

  return (
    <div>
      {criteria.map((c, idx) => (
        <div key={idx}>
          <select
            aria-label={`field-${idx}`}
            value={c.field}
            onChange={(e) => update(idx, { field: e.target.value })}
          >
            <option value="">--</option>
            {FIELDS.map((f) => (
              <option key={f} value={f}>
                {f}
              </option>
            ))}
          </select>
          <select
            aria-label={`operator-${idx}`}
            value={c.operator}
            onChange={(e) => update(idx, { operator: e.target.value })}
          >
            <option value="">--</option>
            {OPERATORS.map((o) => (
              <option key={o} value={o}>
                {o}
              </option>
            ))}
          </select>
          <input
            aria-label={`value-${idx}`}
            value={c.value}
            onChange={(e) => update(idx, { value: e.target.value })}
          />
          <button
            aria-label={`remove-${idx}`}
            type="button"
            onClick={() => remove(idx)}
          >
            Remove
          </button>
        </div>
      ))}
      <button type="button" onClick={add}>
        Add
      </button>
    </div>
  );
}

export default CriteriaBuilder;
