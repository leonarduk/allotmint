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
| `account`   | string | Account identifier within the owner's portfolio. |
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
