import type { CashDeploymentTranche } from '../types';

export const gbp = new Intl.NumberFormat('en-GB', {
  style: 'currency',
  currency: 'GBP',
});
export const units = new Intl.NumberFormat('en-GB', {
  maximumFractionDigits: 4,
});

/** Pence to a £ string. */
export const pounds = (minor: number) => gbp.format(minor / 100);

/** The order list as plain text, for pasting into a note before placing the orders at a broker. */
export function orderListText(tranche: CashDeploymentTranche): string {
  const lines = tranche.orders.map((o) =>
    [
      o.asset_class,
      o.ticker ?? o.vehicle_note ?? '-',
      pounds(o.amount_minor),
      o.indicative_units != null ? `~${units.format(o.indicative_units)}` : '',
    ]
      .filter(Boolean)
      .join('\t')
  );
  return [tranche.label, ...lines].join('\n');
}
