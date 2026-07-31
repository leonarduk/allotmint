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

| Field          | Type   | Description |
| -------------- | ------ | ----------- |
| `owner`        | string | Portfolio owner the transaction belongs to. |
| `account`      | string | Account identifier within the owner's portfolio. |
| `ticker`       | string | Instrument symbol being traded. |
| `type`         | string | Trade direction. Supported values: `BUY` or `SELL`. |
| `shares`       | number | Quantity of shares involved in the trade. |
| `amount_minor` | number | Notional trade value in the smallest currency unit (e.g. pence). |
| `currency`     | string | ISO currency code such as `GBP` or `USD`. |
| `date`         | string | Trade execution date in ISO 8601 format. |

### Optional fields

| Field            | Type   | Description |
| ---------------- | ------ | ----------- |
| `reason_to_buy`  | string | Rationale for the trade; stored for audit and compliance purposes. |
| `security_ref`   | string | Internal security identifier, if known. |
| `kind`           | string | Set to `portfolio` for share transactions or `account` for cash movements. |

## Example request

```bash
curl -X POST https://api.example.com/transactions \
  -H 'Content-Type: application/json' \
  -d '{
        "owner": "alex",
        "account": "isa",
        "ticker": "PFE",
        "type": "BUY",
        "shares": 10,
        "amount_minor": 170000,
        "currency": "USD",
        "date": "2024-03-25",
        "reason_to_buy": "Long-term growth strategy"
      }'
```

## Example response

On success the API responds with the newly created transaction. The
portfolio for `alex` will now include the additional shares and cash
adjustment. Fetch it again using `GET /portfolio/alex` to verify:

```json
{
  "owner": "alex",
  "account": "isa",
  "ticker": "PFE",
  "type": "BUY",
  "shares": 10,
  "amount_minor": 170000,
  "currency": "USD",
  "date": "2024-03-25",
  "reason_to_buy": "Long-term growth strategy"
}
```

```bash
# later
curl https://api.example.com/portfolio/alex
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
