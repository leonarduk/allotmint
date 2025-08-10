import type {Portfolio} from "../types";
import {AccountBlock} from "./AccountBlock";
import {money} from "../lib/money";
import i18n from "../i18n";

// Props accepted by the view. `data` is null until a portfolio is loaded.
type Props = {
    data: Portfolio | null;
    loading?: boolean;
    error?: string | null;
    relativeView?: boolean;
};

/**
 * Render a portfolio tree showing an owner's accounts and holdings.
 *
 * The component is intentionally tiny: it deals only with presentation and
 * relies on its parent for data fetching. Conditional branches early-return to
 * keep the JSX at the bottom easy to follow.
 */
export function PortfolioView({data, loading, error, relativeView = false}: Props) {
    if (loading) return <div>Loading portfolio…</div>; // show a quick spinner
    if (error) return <div style={{color: "red"}}>{error}</div>; // bubble errors
    if (!data) return <div>Select an owner.</div>; // nothing chosen yet

    return (
        <div>
            <h1 style={{marginTop: 0}}>
                Portfolio: <span data-testid="owner-name">{data.owner}</span>
            </h1>
            <div style={{marginBottom: "1rem"}}>
                As of {new Intl.DateTimeFormat(i18n.language).format(new Date(data.as_of))} • Trades this month: {data.trades_this_month} / 20
                (Remaining: {data.trades_remaining})
            </div>
            <div style={{marginBottom: "2rem"}}>
                Approx Total: {money(data.total_value_estimate_gbp)}
            </div>
            {/* Each account is rendered using AccountBlock for clarity */}
            {data.accounts.map((acct) => (
                <AccountBlock key={acct.account_type} account={acct} relativeView={relativeView}/>
            ))}
        </div>
    );
}
