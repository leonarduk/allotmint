# Instrument classification: asset class and fund sector

Instrument metadata (`<data_root>/instruments/<EXCHANGE>/<SYMBOL>.json`) carries
two fields that portfolio breakdowns, the assistant and the technicals
benchmark choice (#9195) depend on:

- **`asset_class`**: one of `equity`, `bond`, `cash`, `commodity`, `property`,
  `multi-asset` (lowercase). "Fund" or "ETF" is a wrapper, not an asset class.
- **`sector`**: for company shares, the company's sector. For funds, trusts and
  ETCs, the sector of what the fund holds, never the issuer's. An iShares or
  Vanguard ETF is not "Financials" just because its manager is a financial
  company (#9196).

## How values are derived

`backend/common/instrument_classification.py` (`classify_instrument`) holds the
rules:

1. **Manual override.** An entry in
   `<data_root>/instrument_classification_overrides.json` always wins.
2. **Cash**: `CASH.*` tickers and cash or money-market instrument types.
3. **Funds and trusts** (type ETF, ETC, mutual fund or investment trust, or a
   name with UCITS, ETF, Fund or Investment Trust): the name decides first
   ("Gilts", "Bond", "Credit" mean bond; "Physical Gold" or "ETC" mean
   commodity; "Real Estate" means property; "LifeStrategy" or "Multi-Asset"
   mean multi-asset; "MSCI", "FTSE", "Stock" or "Equity" mean equity). Next comes the
   provider's category (Yahoo `category`), then a sector that names an asset
   class ("Fixed Income"). If none of these match, the fund is equity. A bare
   "Gold" in the name does not count, because "Gold Producers" ETFs hold
   mining shares.
4. **Company shares** (type Equity): `equity`. A Yahoo `BOND` quote type is
   `bond`. Index, currency, crypto and derivative quote types are left without
   an asset class; if one is held, the data-quality audit flags it.
5. **Fund sector.** If a fund's sector is missing, belongs to the issuer
   (Financials, Financial Services, Miscellaneous) or contradicts the asset
   class (an equity ETF filed under "Fixed Income"), it is replaced with an
   exposure label: `Multi-sector` (equity), `Fixed Income` (bond), `Cash`,
   `Commodities`, `Real Estate` (property) or `Multi-asset`. On an equity fund
   a real sector is kept, for example "Consumer Staples" on a sector ETF or
   "Utilities" on a renewables trust. On a bond, cash, commodity or property
   product the sector is kept only if it names that asset class ("Government
   Bond", "Commodities - Energy"); anything else, such as "Materials" on a gold
   ETC, is replaced.

The rules run in two places:

- **On ingest**: `_fetch_metadata_from_yahoo` classifies new metadata from Yahoo
  `quoteType`, `category` and `sector`.
- **Backfill**: `python -m scripts.classify_instruments [--write]` reclassifies
  every persisted file. It is a dry run by default and can be run again
  safely.

The read path (`get_instrument_meta`) never reclassifies, so what is on disk
(or in S3) is what callers see.

## Manual overrides

When the rules get an instrument wrong, add it to
`<data_root>/instrument_classification_overrides.json` instead of editing the
instrument file. If you only edit the file, the next backfill run can revert
it.

```json
{
  "_comment": "Manual asset_class/sector overrides; see allotmint docs/instrument-classification.md",
  "ESIH.L": {"sector": "Health Care"}
}
```

Each entry may set `asset_class`, `sector` or both. Keys starting with `_` are
ignored. An `asset_class` outside the six values above is logged and ignored. Then run `python -m scripts.classify_instruments --write`.

## Gaps

The data-quality page (`/data-quality`, Issues and Holdings tabs) reports a
`MISSING_ASSET_CLASS` issue for each held instrument whose `asset_class` is
missing or is not one of the values above. Fix it by running the backfill or
adding an override.
