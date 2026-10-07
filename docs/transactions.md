# Transactions API

The `POST /transactions` endpoint records a new trade and updates the
associated portfolio. After a transaction is accepted, the server
recomputes holdings for the specified owner and account so subsequent
calls to [`GET /portfolio/{owner}`](../README.md) reflect the new
state.

## Endpoint

```
POST /transactions
Content-Type: application/json
```

## Required fields

| Field       | Type   | Description |
| ----------- | ------ | ----------- |
| `owner`     | string | Portfolio owner the transaction belongs to. |
| `account`   | string | Account identifier within the owner's portfolio. Case-insensitive: `ISA` and `isa` are the same account, recorded in its existing transactions file (a new account's file is lower-case). The response's `account` and `id` use that file's spelling, so posting `ISA` to a new account returns `isa`. |
| `ticker`    | string | Instrument symbol being traded. |
| `date`      | string | Trade date, `YYYY-MM-DD`. |
| `price_gbp` | number | Price per unit in GBP; must be greater than 0. |
| `units`     | number | Quantity traded; must be greater than 0 (use `type` for direction). |
| `reason`    | string | Rationale for the trade; stored for audit and compliance purposes. |

### Optional fields

| Field         | Type   | Description |
| ------------- | ------ | ----------- |
| `type`        | string | `BUY` (default) or `SELL`. A `SELL` reduces the holding and records a realised gain. |
| `fees`        | number | Dealing fees in GBP: added to a purchase's cost, deducted from a sale's proceeds. |
| `comments`    | string | Free-text note. |
| `external_id` | string | Caller-supplied identifier, e.g. a broker reference. |

Only `BUY` and `SELL` are accepted here; other types (dividends, transfers,
cash movements) come in through `POST /transactions/import`.

`PUT /transactions/{id}` takes the same body. On update `type` has no
default: omit it to keep the stored type, so editing an imported row of
another type (e.g. `DIVIDEND`) does not change it.

The update is type-aware. A row is edited as a trade when the body sets
`type`, or its stored type is `BUY`, `SELL` or missing (legacy untyped
entries): `ticker`, `date`, `price_gbp` and `units` are then required (422
if any is absent) and the body replaces the stored row's fields. Any other
stored type (`DIVIDEND`, `TRANSFER_IN`, ...) keeps its stored `ticker`,
`price_gbp` and `units` whatever the body carries, and its `date` unless
the body gives one, so a body of just `owner`, `account`, `reason` and the
fields being changed (`date`, `fees`, `comments`, `external_id`) is enough.

## Example request

```bash
curl -X POST https://api.example.com/transactions \
  -H 'Content-Type: application/json' \
  -d '{
        "owner": "alex",
        "account": "isa",
        "ticker": "PFE",
        "type": "SELL",
        "date": "2024-03-25",
        "price_gbp": 17.0,
        "units": 10,
        "fees": 5.0,
        "reason": "Take profit"
      }'
```

## Example response

On success the API responds `201` with the stored transaction and its `id`.
The account's holdings are rebuilt from its transactions, so a later
`GET /portfolio/alex` reflects the sale:

```json
{
  "owner": "alex",
  "account": "isa",
  "ticker": "PFE",
  "type": "SELL",
  "date": "2024-03-25",
  "price_gbp": 17.0,
  "units": 10.0,
  "fees": 5.0,
  "comments": null,
  "reason": "Take profit",
  "external_id": null,
  "id": "alex:isa:3"
}
```

## Setting a holding (`POST /holdings/manual`)

Holdings are rebuilt from an account's transactions on every transaction
write, so the holdings input page (`/input`) does not write a holding
directly. It records the transaction that brings the account to the units
entered:

- more units than the transactions add up to: a `TRANSFER_IN` of the
  difference, dated at the account's oldest transaction (today if it has
  none), so it reads as a balance held from the start;
- fewer: a `TRANSFER_OUT` of the difference, dated today (dated earlier it
  could exceed the units held on that date);
- the same: nothing is recorded (`"transaction": null`).

Those dates apply when the body has no `date`. With `date` (ISO, not in the
future) the transfer is dated then instead, with reason
`Set holding from holdings input`; the portfolio page's **Add position** form
sends today's date by default and offers the opening-balance dating as an
explicit checkbox (#9992). The units are always the *total* held afterwards,
not the size of a trade.

Transfers carry `price_gbp` as their cost and have no cash effect. The body
takes `units` + `price_gbp`, or `value_gbp`, which is converted to units at
`price_gbp` if given, else at the cached last close (400 if none is known).

`"dry_run": true` returns the would-be `transaction`, the `units_before` it
offsets and any `price_warning` without writing anything; the Add position
form shows that as a preview before saving. A save whose `price_gbp` is 50x
or more above (or below) the cached last close is rejected with 422 as a
likely pence/pounds mix-up, unless the body sets `"confirm_price": true`.
The check applies only to this endpoint, not to imports or `POST /transactions`.

A rebuild keeps any holding that no transaction mentions, so holdings entered
before this change, or imported as a snapshot, are not dropped. Such a holding
has nothing behind it to sell, though. To give it an opening balance, run
`python -m scripts.convert_untracked_holdings` (see `scripts/README.md`).

## Bulk import

```
POST /transactions/import
Content-Type: multipart/form-data
```

Upload the provider export in the `file` field and identify its format with
the `provider` field. The optional `owner` and `account` fields provide a
destination when rows in the export do not contain one. Rows without a
resolvable destination, or with an invalid owner or account, are returned in
`skipped` with a `skip_reason`.

The response is an object containing separate arrays for transactions written
and rows skipped; it is not a flat array:

```json
{
  "persisted": [
    {
      "id": "alex:isa:0",
      "owner": "alex",
      "account": "isa",
      "ticker": "PFE",
      "price_gbp": 17.0,
      "units": 10
    }
  ],
  "skipped": [
    {
      "ticker": "MSFT",
      "skip_reason": "missing owner/account"
    }
  ]
}
```

Persistence is atomic for the accepted rows in one request. If any write
fails, transactions already written by that import are removed and affected
portfolios are rebuilt before the error is returned.
