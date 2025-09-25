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
