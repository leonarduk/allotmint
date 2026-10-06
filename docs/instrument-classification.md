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

### Legacy capitalised values

Metadata written before #9196 spells asset classes `Equity`, `Bond`,
`Commodity`. Until a data root is backfilled (or while a stale S3 copy is
served), both spellings are in circulation, so consumers compare
case-insensitively:

- Backend: `canonical_asset_class()` and `resolve_instrument_type()` in
  `instrument_classification.py` map `Equity` and `equity` to `equity`. They
  are used by `enrich_holding`, `portfolio_utils.get_security_meta`,
  `prices._resolve_instrument_type` and the report asset-class breakdown
  (which shows `Equity`). An unrecognised label such as `Fund` is kept as is.
- Frontend: `translateInstrumentType` (`src/lib/instrumentType.ts`) and
  `assetClassLabel` (`src/lib/assetClass.ts`) look values up lower-cased.

### Read-time fund sector correction

Until a data root is backfilled, a fund can still carry its issuer's sector
("Financials" on a Vanguard ETF). `exposure_sector()` applies the step 5 rules
when metadata is read, so a fund whose sector is the issuer's, a wrapper or
contradicts its asset class is reported with its exposure label. Company
shares keep their sector. It is used by `enrich_holding`,
`portfolio_utils.get_security_meta`, `aggregate_by_ticker` rows and
`/instrument/search`. The admin instrument listing still shows the stored
value, so what you edit is what is on disk.

Overrides are read once per change of the overrides file (the file's
modification time is checked), so edits take effect without a restart.

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

## Sub-asset classes (Bond, Commodity)

The rebalance page can target Bond and Commodity by sub-class (#9543). Each
held instrument gets a `sub_asset_class` at read time from
`backend/common/sub_asset_class.py`; nothing is written back to disk. The keys
match the asset-class blocks of allotmint-pro's `backtest_portfolio` tool.

| Parent | Sub-class key | Rule (first match wins) |
| --- | --- | --- |
| bond | `index_linked` | name/index mentions inflation-linked, index-linked or linkers |
| bond | `short_gilts` | name/index mentions ultrashort |
| bond | `long_gilts` / `intermediate_gilts` / `short_gilts` | a gilt or UK government fund, banded by `fund_facts.effective_duration_years` (under 3 short, 3-10 intermediate, over 10 long); without a duration, the midpoint of `fund_facts.maturity_band` or a maturity range in the name ("0-5yr", "15+ Year") |
| bond | `corporate_bonds` | corporate, credit, income, investment grade, high yield or loans |
| bond | `overseas_government` | any other government, treasury or bund fund |
| commodity | `gold` | the name or index mentions gold |
| commodity | `commodities` | every other commodity |

To override a sub-class, set `sub_asset_class` on the instrument file or add it
to the override entry, for example `"TFIF.L": {"sub_asset_class": "corporate_bonds"}`.
An override that belongs to a different parent class is logged and ignored.
A bond with no recognised sub-class stays in Bond. When Bond is targeted by
sub-class, the rebalance page shows it in a "Bond — no sub-class" row and a
note. It counts towards the total but is never traded.

## Gaps

The data-quality page (`/data-quality`, Issues and Holdings tabs) reports a
`MISSING_ASSET_CLASS` issue for each held instrument whose `asset_class` is
missing or is not one of the values above. Fix it by running the backfill or
adding an override.
