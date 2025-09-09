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
    "1d": { "baseline": 12345.67, "shocked": 12000.00 },
    "1w": { "baseline": 12345.67, "shocked": 11900.00 }
  }
}
```

Each horizon entry uses a consistent schema:

- `baseline` – the portfolio's value before the event.
- `shocked` – the portfolio's value after applying the event to that
  horizon.

The baseline is repeated for each horizon to simplify downstream
consumers and maintain a single schema for all horizon entries.
