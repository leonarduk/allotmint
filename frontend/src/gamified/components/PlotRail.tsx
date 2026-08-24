import { NavLink } from 'react-router-dom';
import styles from '../plot.module.css';

export interface RailItem {
  to: string;
  label: string;
  subtitle?: string;
  /** Exact match only — used for the hub so children don't light it up. */
  end?: boolean;
}

interface PlotRailProps {
  items: readonly RailItem[];
}

/** Left-hand navigation slabs, the arcade-menu equivalent of the app nav. */
export default function PlotRail({ items }: PlotRailProps) {
  return (
    <nav className={styles.rail} aria-label="Plot sections">
      {items.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.end}
          className={({ isActive }) =>
            isActive
              ? `${styles.railButton} ${styles.railButtonActive}`
              : styles.railButton
          }
        >
          {item.label}
          {item.subtitle && (
            <span className={styles.railSubtitle}>{item.subtitle}</span>
          )}
        </NavLink>
      ))}
    </nav>
  );
}
