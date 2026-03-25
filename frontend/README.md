# AllotMint Frontend

The AllotMint frontend is a React + TypeScript single-page app that visualises family investment data fetched from the backend API.
The backend API must be running and reachable from the browser (local, LAN IP, or deployed URL).

## Interface

- Portfolio viewer for individual owners and groups.
- Watchlist, screener and other analysis pages.
- A **Relative view** toggle in the portfolio table hides absolute columns and shows percentage-based metrics such as "Gain %" and "Weight %".

## Development scripts

- `npm run dev` – start the Vite development server.
- `npm test` – execute the test suite with Vitest and Testing Library.
  Test files should be named `*.test.ts`, `*.test.tsx`, or `*.test.js` to be picked up.

### Smoke test page

For manual diagnostics you can expose a smoke test route that pings key API
endpoints. Start the dev server with the `VITE_SMOKE_TEST` flag to enable the
page at `/smoke-test`:

```bash
VITE_SMOKE_TEST=1 npm run dev
```

### Enabling service workers in development

Push alerts rely on a service worker. The service worker is registered
automatically in production builds, but you can enable it locally by starting the
dev server with the `VITE_ENABLE_SW` flag:

```bash
VITE_ENABLE_SW=1 npm run dev
```

## Routing

The app opts into upcoming React Router v7 behavior by enabling the
`v7_startTransition` and `v7_relativeSplatPath` flags. This allows testing
future navigation features ahead of the final release.

### Routes

- `/` – portfolio overview
- `/discover` – browse curated opportunities
- `/research/:ticker` – research page for a specific ticker
- `/screener` – build and run custom screeners
- `/watchlist` – manage personal watchlists
- `/transactions` – view transaction history
- `/reports` – after selecting an owner, provides CSV/PDF exports

## Installation

1. Install dependencies with `npm install`.
2. Ensure the backend API is running. From the repository root you can start it with `./run-local-api.sh`, which serves `http://localhost:8000` by default.
3. Update `public/config.json` with the backend URL you want this frontend build to use:

   ```json
   {
     "apiBaseUrl": "http://192.168.1.20:8000"
   }
   ```

   At startup, the app fetches `/config.json` and uses that value without requiring a rebuild.

4. If you prefer build-time overrides, set `VITE_ALLOTMINT_API_BASE` (or legacy `VITE_API_URL`) before starting the dev server, e.g.:

   ```bash
   export VITE_ALLOTMINT_API_BASE=http://localhost:8000
   ```
5. Run `npm run dev` and open the app in your browser.
6. Use the browser's **Install** or **Add to Home Screen** option to install the PWA. The service worker caches static assets for offline use.

## Configuration

Preferred runtime setting:

* `public/config.json` with `{ "apiBaseUrl": "https://..." }` – allows one build to switch backends without rebuilding.

Optional build-time environment variables:

* `VITE_ALLOTMINT_API_BASE` – full base URL to the backend.
* `VITE_API_URL` – legacy fallback used when `VITE_ALLOTMINT_API_BASE` is unset.
* `VITE_API_TOKEN` – optional token sent as `X-API-Token` with every request.
* `VITE_GIT_COMMIT` / `VITE_GIT_BRANCH` – optional git metadata shown on the Support page for build provenance (set them manually or rely on `build.sh` / `scripts/deploy-to-aws.sh`).

To provide the token, add it to your environment or a `.env` file in `frontend`:

```
VITE_API_TOKEN=your-token-here
```

Resolution order is:
1. `/config.json` → `apiBaseUrl` (runtime, no rebuild).
2. `VITE_ALLOTMINT_API_BASE`.
3. `VITE_API_URL` (legacy).
4. `http://localhost:8000`.

Runtime feature flags and tab visibility come from the backend's `config.yaml`. See the [backend setup instructions](../README.md#local-quick-start) for configuring and running the server.

## Tab plugins

Tabs in the navigation bar are driven by a small plugin system. A plugin
provides the component to render and optional metadata such as a
`priority` value. Plugins are registered in `src/pluginRegistry.ts`.

```ts
import { registerTabPlugin } from './pluginRegistry';
import MyTab from './pages/MyTab';

registerTabPlugin({
  id: 'myTab',
  Component: MyTab,
  priority: 50, // higher numbers appear earlier
});
```

Plugins with higher priority numbers are displayed before lower ones. A
plugin can be disabled by setting `isEnabled` to `false` or providing a
function that returns `false`.
