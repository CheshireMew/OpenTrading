# OpenTrading architecture boundaries

OpenTrading uses a small inward-facing core and an explicit outer runtime shell.

Cross-asset history and dollar liquidity are part of these same layers: values and calculations live in `app/domain/market/history` and the market liquidity modules, remote clients in `app/infra/market_data`, records and artifacts in `app/infra/persistence/market/history`, and orchestration in `app/services/market`. They use `AppSettings`, the shared database engine, Alembic migrations and the existing background lifecycle. Their CLI entry is `python -m scripts.market_data_cli`; there is no separate `signal_lab` package or application version. Existing `/signal-lab` API paths, database table names, snapshot identities and artifact locations remain compatible.

`app/domain` owns business values and rules. It cannot import HTTP contracts, runtime services, infrastructure, or routers. `app/application` owns use cases, ports, and application errors. It can depend on the domain, but not on contracts, infrastructure, services, routers, or FastAPI.

`app/services` is deliberately the outer orchestration layer, not the application core. It adapts transport commands, schedules blocking work on the named executors, coordinates external clients, and returns transport-ready results. Its ability to use `app/contracts` and `app/infra` is intentional; inner layers must never import it.

`app/infra` implements application ports and owns databases, caches, executors, and external clients. It may depend on `app/application` and `app/domain`, but never on transport contracts, routers, service orchestration, or application-wide HTTP exceptions. Infrastructure reports domain or application errors; `app/main.py` maps those errors to the single HTTP error contract.

`app/contracts` and `app/routers` form the HTTP boundary. Generated frontend types and route maps come only from these FastAPI routes. `app/runtime.py` is the composition root that wires concrete outer adapters to inner ports.

The chart workspace is initialized once by `AppRuntimeServices.start` and closed before the other API adapters. Its runtime owns an OS file lock for the workspace directory; requests only retrieve this runtime. Seeding is transactionally idempotent, and only the runtime owner recovers interrupted Pine runs. Workspace SQLite transactions, run metadata and record queries use the dedicated workspace executor, never the API event loop. Cancellation waits for any in-flight process creation to return its actual OS handles before reclaiming the worker.

Quotes carry observation time separately from request time, source and validity. Expired quotes remain explicitly stale. Daily simulation and analytics consume closed history and preserve coverage failures; continuous markets require each daily observation, while exchange-session histories can carry a verified previous close across non-trading dates. Pine document operations bind responses to the original document and selection generation.

Workspace repositories live in `app/infra/persistence`; their value objects live in `app/domain/chart_workspace`. Services load the two active built-in scripts and submit transactional defaults. Network and database drivers belong to infrastructure, including exchange, index, indicator, currency, equity-catalog and websocket clients; services do not import those drivers directly.

Chart history and `scripts.market_data_cli data crypto-sync` share `KlineStore` and `HistoryRangeCoordinator`. Closed history is reused before requesting gaps; current chart candles remain live observations. Spot and perpetual histories have separate storage identities. Larger periods use the shared synthesis rules without storing duplicate derived rows. Cross-asset daily snapshots remain immutable research evidence rather than an alternative intraday cache.

Pair comparisons read the selected native candle period and exclude its current open candle. DCA loads only the selected strategy's required warm-up and computes only its indicators. Large asynchronous cache values are encoded and decoded on the compute executor; synchronous cache callers retain their existing behavior. Concurrent identical tool requests share one calculation, and cancellation of one HTTP observer does not cancel the shared work.

Exchange symbol catalogs refresh independently, retain each venue's last verified metadata on failure, and publish as soon as one venue is ready. Resolving a known symbol never waits for an unrelated venue. Hidden chart pages suspend plot subscriptions; explicit live-order subscriptions remain active. Resuming repairs the last forming candle and intervening history before delivering buffered live chart bars. Repair bars never execute live orders, and server alert monitoring has an independent lifetime.

Data-health history repair splits its supported date range into non-overlapping windows within `FULL_HISTORY_MAX_POINTS`. Its response distinguishes `completed` from `partial` and carries the remaining UTC gaps or missing trading sessions. The frontend displays that coverage instead of treating a successful HTTP request as proof of complete history.

Migration `021_confirmed_candle_history` preserves old OHLCV rows as unconfirmed. Reads hydrate only requested windows to confirm final closes; they never treat a cached open bar as final merely because time passed. Live observations stay separate from finalized history. Index coverage uses XNYS, XSHG and XHKG calendars and exposes missing sessions and verified non-trading dates. Unknown calendar ranges fail closed. Signal evaluations require continuous, closed history inside the entry/expiry window, and horizon returns use candle close times.


## Responsibility owners after the cohesion refactor

Historical source, strategy versions, design drafts and verification material are retained only in ignored `archived/`. `.runtime/` owns tests, tool caches and task artifacts; `.opentrading_runtime/` owns current application data and runtime state. Required Pine regression fixtures live in `frontend/test/fixtures/pine-runtime/` and do not depend on local archives.

Strategy simulation has one active owner: the chart workspace Pine/PineTS strategy tester. Python strategy execution, parameter sweeps, granular research diagnostics and their result indexes are archived under `archived/python_backtest_20261123`. Their HTTP and frontend routes, CLI commands and background queue workers are unregistered. Application startup no longer creates research-result SQLite indexes. Migration 024 removes the retired backtest, portfolio and report tables and their data at the user’s explicit request. Shared OHLCV history, its compressed archive, Pine and DCA remain independent.

The frontend chart page composes six owners: chart SDK lifecycle, layout persistence, watchlists and quote polling, Pine document drafts, Pine execution and panel interaction. Each owner controls its request generations, timers and cleanup. It receives only its required capability callbacks, not the entire page state. The two backend periodic evaluators share `PeriodicTask` lifecycle code while retaining independent business evaluation rules.

Real-time and historical EMA, RSI, MACD and ATR use `TechnicalAnalysis` series calculations. Historical projections align their warm-up values without reimplementing the algorithms. The v3 indicator contract records SMA-seeded smoothing and a neutral flat RSI of 50; its registry identity prevents reuse of older indicator artifacts. Binance alerts, screeners, public observations and asset research share `BinanceMarketObservations`, including market identity and funding-rate percentage conversion.

`MarketDataRuntime` composes one explicit `MarketHistoryDatabase` and the history services that use it. CLI contexts, HTTP views, chart history and job workers receive this dependency directly; no context-variable database binding is required. Dataset services receive the same price, indicator and classification services from this composition root. File-format writing and verification live in persistence adapters; `ArtifactPublisher` owns capacity checks, temporary-file publication, immutable Parquet/export validation and failure recording.

Workspace alerts compose live-rule persistence, replay-session evaluation and chart interaction owners. The replay component composes playback/date navigation, account commands, chart interaction and trade projection. Each owner releases its own polling, event listeners, subscriptions and chart marks; the Vue component retains presentation layout.

Pine sources remain in `strategies/pine`; the old Python strategies, authoring templates and standalone-snapshot checks are archived with their engine. Generated contracts cover only active HTTP routes.

Portfolio balance, ledger/simulation/analytics, report generation and portfolio-drift alerts are archived under `archived/portfolio_balance_20261123`. They have no active pages, API, CLI, startup service or new-alert input. Legacy database data is deleted by migration 024; archived source is retained for reference.
