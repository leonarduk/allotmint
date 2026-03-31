import type { VarBreakdown } from "../types";

interface Props {
  contributions: VarBreakdown[];
  onClose: () => void;
}

export function VarBreakdownModal({ contributions, onClose }: Props) {
  const hasRows = contributions.length > 0;

  return (
    <div
      role="dialog"
      aria-modal="true"
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        background: 'rgba(0,0,0,0.3)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <div
        style={{
          background: "var(--surface-card-bg, #fff)",
          color: "var(--surface-card-color, #111)",
          border: "1px solid var(--surface-card-border, #d9d9d9)",
          padding: "1rem",
          maxHeight: "80%",
          minWidth: "20rem",
          overflow: "auto",
        }}
      >
        <h3>VaR Breakdown</h3>
        {hasRows ? (
          <table>
            <thead>
              <tr>
                <th style={{ textAlign: "left", paddingRight: "1rem" }}>Ticker</th>
                <th style={{ textAlign: "right" }}>Contribution</th>
              </tr>
            </thead>
            <tbody>
              {contributions.map((c) => (
                <tr key={c.ticker}>
                  <td style={{ paddingRight: "1rem" }}>{c.ticker}</td>
                  <td style={{ textAlign: "right" }}>{c.contribution.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p style={{ margin: 0 }}>No contribution data available.</p>
        )}
        <button onClick={onClose} style={{ marginTop: '1rem' }}>
          Close
        </button>
      </div>
    </div>
  );
}

export default VarBreakdownModal;
