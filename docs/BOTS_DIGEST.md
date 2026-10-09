# Bots digest (#10485)

One ranked weekly or monthly summary of what every bot found that needs the
owner. It replaces one alert per bot.

## Contract for bots: `digest_items`

Each bot's stored run record carries a `digest_items` list. The digest only
ever restates these items. The model lives in `backend/bots/digest_models.py`
(`DigestItem`, `BotRunRecord`):

| Field | Meaning |
|---|---|
| `id` | Unique within the run |
| `bot` | Bot id (the composer overwrites it with the id of the bot whose run reported the item) |
| `owner` | Owner the item is about; `null` for a system-wide item (admins only) |
| `severity` | `high` / `medium` / `low` / `info` |
| `title`, `summary` | The bot's own factual wording. No advice. |
| `link` | App-relative (`/...`) or `https://` link to the report or action; anything else is dropped |
| `action_required` | `true` when the owner has to do something |
| `created` | ISO timestamp (naive timestamps are treated as UTC) |
| `dedupe_key` | Stable id for "the same finding" across runs: drives new / still open / resolved |

Run records are read from `<BOTS_RUNS_URI>/<bot_id>/latest.json` (default
`{data_root}/bots/runs`) through `RunRecordSource` in
`backend/bots/run_records.py`. When the bot registry (#10477) lands, it can
implement that interface (and replace `KNOWN_BOTS`) without changes to the
composer. A run with `status: "failed"` becomes a high-severity item on its own.

## Composer

`backend/bots/digest.py` is deterministic. It ranks by severity, then
`action_required`, then age (oldest first), and caps the number of items per
bot (the count of dropped items is shown). It compares items by `dedupe_key`
with the previous stored digest to label them **new** or **still open**.
Previously open items that are gone appear once as **resolved**. A bot with no
run is listed as "not run yet". An optional opener function (e.g. an LLM) is
used only when every number in its text comes from the items. Otherwise the
plain opener is used.

## Storage, settings and delivery

| Env var | Default | Holds |
|---|---|---|
| `BOTS_RUNS_URI` | `{data_root}/bots/runs` | Bot run records (read only) |
| `BOTS_DIGESTS_URI` | `{data_root}/bots/digests` | `<owner>/<date>.json`, `latest.json`, `index.json`, `alerted.json` |
| `BOTS_DIGEST_SETTINGS_URI` | `file://{data_root}/bots/digest_settings.json` | Per-owner settings, keyed by owner |
| `BOTS_DIGEST_OWNERS` | all owners | Comma-separated owners for the Lambda |
| `BOTS_DIGEST_FROM` | `no-reply@allotmint.com` | SES sender |

Per-owner settings (`backend/bots/digest_settings.py`) and their defaults:

- `period`: `weekly` (sent Mondays). Can be `monthly` (sent on the 1st).
- `email_enabled`: `true`.
- `telegram_enabled`: `false`.
- `include_balances`: `false`. £/$/€ amounts are hidden in email and Telegram unless this is `true`.
- `send_when_empty`: `false`.
- `per_bot_cap`: `5`.
- `alert_immediately_for`: `{}`, e.g. `{"allowance-guardian": ["high"]}`. Matching items alert straight away through the trading-agent transports (`send_trade_alert`), once per open `dedupe_key`, and still appear in the digest.

`backend/lambda_api/bots_digest.py` runs daily. It always sends immediate
alerts. On the owner's digest day (or with `{"force": true}`) it also saves and
delivers the digest.

## API

- `GET /bots/digest/{owner}/latest`: the latest stored digest, or 404 if there is none yet.
- `GET /bots/digest/{owner}/history?limit=8`: stored digests, newest first.
- `GET /bots/digest/{owner}/preview`: the digest as it would be composed now. Nothing is saved or sent.

All three check owner access. System-wide items are returned to admins only.
