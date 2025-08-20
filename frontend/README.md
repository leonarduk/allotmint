# AllotMint Frontend

The AllotMint frontend is a React + TypeScript single-page app that visualises family investment data fetched from the backend API.

## Interface

- Portfolio viewer for individual owners and groups.
- Watchlist, screener and other analysis pages.
- A **Relative view** toggle in the portfolio table hides absolute columns and shows percentage-based metrics such as "Gain %" and "Weight %".

## Development scripts

- `npm run dev` – start the Vite development server.
- `npm test` – execute the test suite with Vitest and Testing Library.

## Installation

1. Install dependencies with `npm install`.
2. Run `npm run dev` and open the app in your browser.
3. Use the browser's **Install** or **Add to Home Screen** option to install the PWA. The service worker caches static assets for offline use.

## Configuration

Set one of the following environment variables to tell the UI where the backend lives:

- `VITE_ALLOTMINT_API_BASE` – full base URL to the backend.
- `VITE_API_URL` – legacy fallback used when `VITE_ALLOTMINT_API_BASE` is unset.

If neither is provided the app falls back to `http://localhost:8000`.

Runtime feature flags and tab visibility come from the backend's `config.yaml`. See the [backend setup instructions](../README.md#local-quick-start) for configuring and running the server.
