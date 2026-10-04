# NAV and premium/discount for investment trusts

For a listed closed-end fund (for example a UK investment trust), the main
valuation number is its premium or discount to net asset value (NAV):

```
premium_discount = price / NAV - 1        (negative = discount)
```

`backend/common/nav.py` works this out. The results are available here:

- `GET /instrument/nav-discount?ticker=3IN.L`
- the chat assistant's `get_nav_discount` tool (`backend/chat/nav_discount_tool.py`).
  It runs in-process and is switchable on the admin page like the other tools
  (`mcp.mcp_tools`).

## Where NAVs come from

No free source publishes UK trust NAVs in a form the app may fetch
automatically. NAVs are therefore **recorded as data**, behind a pluggable
`NavProvider` interface:

| Provider | Reads | Notes |
|---|---|---|
| `CsvNavProvider` | `s3://$DATA_BUCKET/nav/navs.csv` when `DATA_BUCKET` is set, else `<data_root>/nav/navs.csv`, else the bundled `data/nav/navs.csv` | The main store. Each row is one published NAV. The S3 copy is cached for 5 minutes; a local file is re-read when it changes. |
| `MetadataNavProvider` | `nav_per_share`, `nav_currency`, `nav_as_of` in the instrument's metadata JSON | The same keys allotmint-pro's valuation profile reads. `nav_currency` is required. |

The NAV with the latest date wins. A dated NAV beats an undated one. A licensed
data feed can be added later as another provider without changing callers.

### Getting `navs.csv` to the deployed app

The file lives in allotmint-data at `nav/navs.csv`. Nothing syncs that repo
to AWS automatically, so after editing it, upload it from the allotmint-data
checkout:

```bash
aws s3 cp nav/navs.csv "s3://$DATA_BUCKET/nav/navs.csv"
```

The Lambda's `data_root` (`/tmp/data`) is empty, so S3 is the live source. A
new upload is picked up within the 5-minute cache, with no redeploy. If the
object is missing, the backend uses the copy baked into the image at
`/var/task/data/nav/navs.csv`, as of the last deploy. If S3 fails for any
other reason (for example, access denied), it logs a warning and uses the same
baked-in copy.

Retyping an instrument as `Investment Trust` changes its metadata JSON. That
change must also reach `s3://$DATA_BUCKET/instruments/` (`METADATA_BUCKET`),
or the deployed app keeps treating the instrument as an equity. See
[DEPLOY.md](DEPLOY.md#investment-trust-navs-and-instrument-metadata).

### `navs.csv` format

```csv
ticker,nav,currency,nav_date,source
3IN.L,380.5,GBX,2026-09-30,RNS 2026-10-01
HICL.L,1.582,GBP,2026-09-30,Factsheet
SERE.L,1.02,EUR,2026-06-30,Half-year report
```

- `ticker` is the full ticker with its exchange suffix.
- `nav` is the NAV per share, exactly as published.
- `currency` is **required**. Use `GBX` for pence and `GBP` for pounds; other
  ISO codes are converted at the latest cached FX rate and flagged with
  `fx_converted`. A row without a currency is skipped and logged, because
  380.5 could be pence or pounds.
- `nav_date` is the date the NAV is struck at (`YYYY-MM-DD`), not the
  announcement date. Leave it empty only if it is unknown. The NAV is then
  compared with the latest close and a warning is added.
- `source` is free text for provenance. It defaults to `manual`.

Several rows per ticker are fine: the file can keep NAV history, and the
latest-dated row is used. Copy NAVs from the trust's RNS "Net Asset Value"
announcement or its factsheet.

## Which instruments get a NAV

Only instruments whose metadata `instrument_type` / `instrumentType` is one of
`Investment Trust`, `Investment Company`, `Closed-End Fund` or `VCT` (case
does not matter). Every other instrument returns `applicable: false` with a
`reason`. Many trusts are currently typed `Equity`, `Fund` or `Real Estate` in
the instrument metadata, so retype them before expecting a NAV.

## How the number is computed

1. Take the latest NAV for the ticker and convert it to GBP. Pence are divided
   by 100 exactly; other currencies use the cached FX rate.
2. Take the cached GBP close **on the NAV date**, or up to four days before it,
   through the holdings pricing path (scaling overrides apply, and no live
   fetch is made on the request). `price_date` is the date of that close.
3. If price/NAV falls outside 0.2–5, the cause is almost certainly a unit
   mix-up (pence vs pounds). The result keeps `premium_discount` null and
   gives that `reason` instead of showing the number.

The response includes `premium_discount` (a fraction) and
`premium_discount_pct` (a percentage).

## Sources considered and rejected (October 2026)

- **Yahoo `navPrice`** is empty for LSE trusts. It is only set for ETFs, and
  then not in the quote currency. Yahoo's terms also restrict automated use.
- **Yahoo `bookValue`** is the last *reported* NAV, which is often months old
  and sometimes in another currency. allotmint-pro already uses it as a
  fallback.
- **AIC (theaic.co.uk)**: its Terms of Use prohibit robots, scraping and data
  mining without written consent.
- **LSE RNS / Investegate web pages** are for manual viewing. Automated access
  requires the paid LSEG RNS feed.
- **Morningstar / Fundamental Data, Xignite** require a paid licence. They are
  a candidate for a future provider.
