import type { VarBreakdown } from "../types";

interface Props {
  contributions: VarBreakdown[];
  onClose: () => void;
}

export function VarBreakdownModal({ contributions, onClose }: Props) {
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
      <div style={{ background: 'white', padding: '1rem', maxHeight: '80%', overflow: 'auto' }}>
        <h3>VaR Breakdown</h3>
        <table>
          <thead>
            <tr>
              <th>Ticker</th>
              <th>Contribution</th>
            </tr>
          </thead>
          <tbody>
            {contributions.map((c) => (
              <tr key={c.ticker}>
                <td>{c.ticker}</td>
                <td>{c.contribution.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <button onClick={onClose} style={{ marginTop: '1rem' }}>
          Close
        </button>
      </div>
    </div>
  );
}

export default VarBreakdownModal;
