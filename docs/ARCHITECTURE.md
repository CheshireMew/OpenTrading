# OpenTrading architecture boundaries

OpenTrading uses a small inward-facing core and an explicit outer runtime shell.

`app/domain` owns business values and rules. It cannot import HTTP contracts, runtime services, infrastructure, or routers. `app/application` owns use cases, ports, and application errors. It can depend on the domain, but not on contracts, infrastructure, services, routers, or FastAPI.

`app/services` is deliberately the outer orchestration layer, not the application core. It adapts transport commands, schedules blocking work on the named executors, coordinates external clients, and returns transport-ready results. Its ability to use `app/contracts` and `app/infra` is intentional; inner layers must never import it.

`app/infra` implements application ports and owns databases, caches, executors, and external clients. It may depend on `app/application` and `app/domain`, but never on transport contracts, routers, service orchestration, or application-wide HTTP exceptions. Infrastructure reports domain or application errors; `app/main.py` maps those errors to the single HTTP error contract.

`app/contracts` and `app/routers` form the HTTP boundary. Generated frontend types and route maps come only from these FastAPI routes. `app/runtime.py` is the composition root that wires concrete outer adapters to inner ports.

The chart workspace is initialized once by `AppRuntimeServices.start` and closed before the other API adapters. Its runtime owns an OS file lock for the workspace directory; requests only retrieve this runtime. Seeding is transactionally idempotent, and only the runtime owner recovers interrupted Pine runs. Workspace SQLite transactions, run metadata and record queries use the dedicated workspace executor, never the API event loop. Cancellation waits for any in-flight process creation to return its actual OS handles before reclaiming the worker.

Quotes carry observation time separately from request time, source and validity. Expired quotes remain explicitly stale. Daily simulation and analytics consume closed history and preserve coverage failures; continuous markets require each daily observation, while exchange-session histories can carry a verified previous close across non-trading dates. Pine document operations bind responses to the original document and selection generation.

Migration `021_confirmed_candle_history` preserves old OHLCV rows as unconfirmed. Reads hydrate only requested windows to confirm final closes; they never treat a cached open bar as final merely because time passed. Live observations stay separate from finalized history. Index coverage uses XNYS, XSHG and XHKG calendars and exposes missing sessions and verified non-trading dates. Unknown calendar ranges fail closed. Signal evaluations require continuous, closed history inside the entry/expiry window, and horizon returns use candle close times.


## Responsibility owners after the cohesion refactor

Strategy simulation has one active owner: the chart workspace Pine/PineTS strategy tester. Python strategy execution, parameter sweeps, granular research diagnostics and their result indexes are archived under `archived/python_backtest_20261123`. Their HTTP and frontend routes, CLI commands and background queue workers are unregistered. Application startup no longer creates research-result SQLite indexes. Migration 024 removes the retired backtest, portfolio and report tables and their data at the user’s explicit request. Shared OHLCV history, its compressed archive, Pine and DCA remain independent.

The frontend chart page composes six owners: chart SDK lifecycle, layout persistence, watchlists and quote polling, Pine document drafts, Pine execution and panel interaction. Each owner controls its request generations, timers and cleanup. It receives only its required capability callbacks, not the entire page state. The two backend periodic evaluators share `PeriodicTask` lifecycle code while retaining independent business evaluation rules.

Pine sources remain in `strategies/pine`; the old Python strategies, authoring templates and standalone-snapshot checks are archived with their engine. Generated contracts cover only active HTTP routes.

Portfolio balance, ledger/simulation/analytics, report generation and portfolio-drift alerts are archived under `archived/portfolio_balance_20261123`. They have no active pages, API, CLI, startup service or new-alert input. Legacy database data is deleted by migration 024; archived source is retained for reference.
