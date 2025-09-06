# Screener Builder

The Screener Builder provides a fluent interface for composing custom equity screeners.
It outputs a `CustomQuery` object that can be sent to the backend with
`runCustomQuery` or saved via `saveCustomQuery`.

```ts
import { ScreenerBuilder, runCustomQuery, saveCustomQuery } from "../frontend";

const query = new ScreenerBuilder()
  .between("2024-01-01", "2024-06-30")
  .owners(["alice", "bob"])
  .tickers(["AAA", "BBB"])
  .metrics(["market_value_gbp", "gain_gbp"])
  .build();

const rows = await runCustomQuery(query);
await saveCustomQuery("H1 performance", query);
```

Each builder method returns the instance, allowing calls to be chained.
Calling `build()` returns the `CustomQuery` structure consumed by the API.
