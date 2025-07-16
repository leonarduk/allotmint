import React from "react";
import type { Account } from "../types";
import { HoldingsTable } from "./HoldingsTable";

type Props = { account: Account; };

export function AccountBlock({ account }: Props) {
  return (
    <div style={{ marginBottom: "2rem", padding: "1rem", border: "1px solid #ddd", borderRadius: "4px" }}>
      <h2 style={{ marginTop: 0 }}>
        {account.account_type} ({account.currency})
      </h2>
      <div style={{ marginBottom: "0.5rem" }}>
        Est Value: £{account.value_estimate_gbp.toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2})}
      </div>
      {account.last_updated && (
        <div style={{ fontSize: "0.8rem", color: "#666" }}>
          Last updated: {account.last_updated}
        </div>
      )}
      <HoldingsTable holdings={account.holdings} />
    </div>
  );
}
