# Data Sources

Heimdall uses a small set of public data sources. Runtime configuration lives in `.env`; application defaults live in `config/settings.py`.

## Required

- `DATABASE_URL`: the only database entrypoint. Use PostgreSQL for normal use; SQLite is used by tests.
- Binance public APIs: spot, USD-M futures, and Web3 endpoints are configured by the `BINANCE_*` settings.

## Optional

- `FRED_API_KEY`: preferred source for US macro indicators such as Treasury yields, federal funds rate, M2, CPI, and credit spreads.

## Fallbacks

- YFinance is used as a fallback for selected market and macro series.
- BaoStock and AkShare are used for China and Hong Kong index history where configured.
- Alternative.me provides Fear & Greed data.
- Mempool.space and DefiLlama provide selected on-chain and stablecoin liquidity inputs.
- Binance PAXG is used as the crypto-native gold proxy.

## Diagnostics

```powershell
.\venv\Scripts\python.exe -m scripts.diagnose_runtime
.\venv\Scripts\python.exe -m scripts.diagnose_runtime --external
```

The default command verifies local runtime construction. `--external` also calls public data APIs and may be slower or rate-limited.
