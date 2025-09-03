# Value at Risk (VaR)

This page describes the historical simulation approach used in AllotMint.

## Inputs

- **owner** – portfolio identifier
- **window size** – number of days of lookback (e.g. 365)
- **confidence** – confidence level such as 95% or 99%
- **include_cash** – whether to include cash balances in the portfolio value

## Algorithm

1. **Reconstruct portfolio value history.**
   For each day \(t\) in the window obtain the portfolio value \(V_t\). If `include_cash` is
   `false`, subtract cash from the value.
2. **Compute returns.**
   The \(k\)-day return from day \(t-k\) to \(t\) is
   \[
   r_{k,t} = \frac{V_t - V_{t-k}}{V_{t-k}} = \frac{V_t}{V_{t-k}} - 1.
   \]
   Daily returns use \(k=1\); 10-day returns use \(k=10\).
3. **Quantile calculation.**
   Let \(r_k\) be the series of \(k\)-day returns. The loss quantile at confidence
   \(\alpha\) is
   \[
   q = \mathrm{quantile}_{1-\alpha}(r_k).
   \]
4. **Scale by current value.**
   With current portfolio value \(V_0\),
   \[
   \mathrm{VaR}_{k,\alpha} = -q \times V_0.
   \]

## Example

Consider a portfolio worth \(V_0 = £200{,}000\). Over the last five days the daily returns were:

| Day | Return |
|----:|-------:|
| 1 | −1.0% |
| 2 | 0.8% |
| 3 | −2.5% |
| 4 | 1.2% |
| 5 | −0.4% |

Sorted returns: [−2.5%, −1.0%, −0.4%, 0.8%, 1.2%]. The 5% quantile is −2.5%,
so the 1‑day 95% VaR is

\[
\mathrm{VaR}_{1,95\%} = 0.025 \times £200{,}000 = £5{,}000.
\]

A 10‑day VaR follows the same procedure using 10‑day returns.
