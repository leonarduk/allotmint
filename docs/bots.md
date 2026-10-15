# Bots: scheduled jobs and AI agents

The **Bots** page (Insights menu, `/bots`) lists every automated job the app
runs, with its last run, run history, **Run now** and settings (#10477). The
backend lives in `backend/bots/`; the API in `backend/routes/bots.py`.

## Adding a bot

1. Write a class with the attributes of `backend.bots.registry.Bot`:
   `id` (lower-case, dashes), `name`, `description`, `kind`
   (`"ai" | "rules" | "job"`), `scope` (`"system" | "owner"`),
   `settings_model`, `default_schedule`, `timeout_minutes`,
   `default_settings()` and `run(context, settings) -> RunResult`.
2. `settings_model` subclasses `BotSettings` (which brings `enabled` and
   `cadence`). It is served with its JSON schema and rendered as a form, so it
   must hold **public, non-secret values only** — never API keys. Put caps
   (tokens, tool calls, items) here and enforce them in `run`.
3. `run` returns a `RunResult`: `status` (`ok | partial | failed | skipped`),
   a short `summary` ("3 holdings flagged"), an optional small `report`, and
   for AI bots `model`, `tokens_in`, `tokens_out`, `cost_usd`. It may raise:
   the runner records a `failed` run with the traceback. Never report a run
   that found nothing as `ok`. Keep personal financial data out of
   `summary`/`report` (counts, not values).
4. Register it: `register_bot(MyBot())` at import, and import the module at
   the bottom of `backend/bots/adapters.py`.

## Running

- **Scheduled**: the Lambda handler calls
  `backend.bots.runner.handle_lambda_event("<bot-id>", event)` inside
  `system_job_context()`. EventBridge rules stay in CDK and fire at the most
  frequent cadence the bot supports; the runner records a `skipped` run when
  the bot is disabled or not due for its `cadence`. Direct invocations (deploy
  Trigger, CI warm-up) always run.
- **Scheduled on a local server** (`app_env: local`, #10925): there is no
  EventBridge, so `backend/bots/local_scheduler.py` fires the bots listed in
  `local_bot_schedule` (config.yaml, `server` section) at their
  `default_schedule` through `runner.execute(..., "schedule")` -- the same
  enabled/due/in-progress checks as a Lambda firing. The default is
  `[price-refresh, dividend-refresh]`; bots that send external messages
  (trading agent, pension report, trend watch, data steward) run on a schedule
  locally only when listed. On startup a bot whose latest slot was missed while
  the server was down runs once straight away. `[]` schedules nothing; any
  other `app_env` schedules nothing locally, so a deployment never runs a bot
  twice. Run one server process: each process starts its own scheduler. The
  Bots page shows "Not scheduled on this server" (no Next run) for scheduled
  bots this server never fires, and flags a scheduled bot as **Overdue** when
  its last completed run is older than twice its schedule/cadence period.
- **Event-driven** (e.g. on upload): set `default_schedule = None` and call
  `backend.bots.runner.execute("<bot-id>", "event", owner=..., payload=...)`.
  `statement-reconciliation` (`backend/reconciliation/bot.py`) is the worked
  example: the upload route does the work and records one run with a closed,
  counts-only payload, and the bot's `run` catches every exception itself so a
  message that could quote the statement never reaches the run record.
- **Run now** (`POST /bots/{id}/run`, admin only): refused with 409 while a
  run is in progress. Locally it runs as a FastAPI background task; on AWS the
  backend invokes the bot's Lambda asynchronously (`BOT_LAMBDA_FUNCTIONS` in
  CDK) with the run id.

Every run writes one record to `BOTS_STORAGE_URI` (`runs/<bot-id>.json`, last
50 runs; `s3://<data bucket>/bots` on AWS, `data/bots` locally). Settings
changes go through `PUT /bots/{id}/settings`, are validated against
`settings_model` (422 on bad values) and written to the admin audit log.
