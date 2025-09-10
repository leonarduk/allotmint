# Historical Scenario Response Schema

The `/scenario/historical` endpoint returns an array of results, one for
each portfolio owner. Each result contains the owner's baseline total
portfolio value and a set of horizon entries describing the shocked
value after applying the historical event.

```json
{
  "owner": "string",
  "baseline_total_value_gbp": 12345.67,
  "horizons": {
    "1d": {
      "baseline_total_value_gbp": 12345.67,
      "shocked_total_value_gbp": 12000.0
    },
    "1w": {
      "baseline_total_value_gbp": 12345.67,
      "shocked_total_value_gbp": 11900.0
    }
  }
}
```

Each horizon entry uses a consistent schema:

- `baseline_total_value_gbp` – the portfolio's value before the event.
- `shocked_total_value_gbp` – the portfolio's value after applying the event to that
  horizon.

The baseline is repeated for each horizon to simplify downstream
consumers and maintain a single schema for all horizon entries.
