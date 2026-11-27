# Data Sources

OpenTrading uses a small set of public data sources. Runtime configuration lives in `.env`; application defaults live in `config/settings.py`.

## Required

- `DATABASE_URL`: the only database entrypoint. Use PostgreSQL for normal use; SQLite is used by tests.
- Binance public APIs: spot, USD-M futures, and Web3 endpoints are configured by the `BINANCE_*` settings.
- Crypto candles and Bitcoin technical indicators use native public REST endpoints. The supported exchange gateways are `binance`, `binanceusdm`, and `okx`; they reuse bounded connection pools without loading exchange-wide market tables. Chart candles share the existing history store with research and CLI readers. Failed upstream reads remain errors and are never cached as an empty history boundary.

## Fallbacks

- YFinance is used as a fallback for selected index price series.
- BaoStock and AkShare are used for China and Hong Kong index history where configured.
- Alternative.me provides Fear & Greed data.
- Mempool.space and DefiLlama provide selected on-chain and stablecoin liquidity inputs.

Market signals collect on-chain, sentiment, and Bitcoin technical data. Macro indicator collection and FRED integration were retired on 2026-10-17. Existing macro history remains stored for reference, but is excluded from indicator responses and data-health freshness checks. Stock catalogs, index price history and benchmark currency conversion remain available without a FRED API key. Retired source snapshots are kept only in local archives and are not included in this repository.

## Diagnostics

```powershell
.\venv\Scripts\python.exe -m scripts.diagnose_runtime
.\venv\Scripts\python.exe -m scripts.diagnose_runtime --external
```

The default command verifies local runtime construction. `--external` also calls public data APIs and may be slower or rate-limited.
