# Data Sources

OpenTrading uses a small set of public data sources. Runtime configuration lives in `.env`; application defaults live in `config/settings.py`.

## Required

- `DATABASE_URL`: the only database entrypoint. Use PostgreSQL for normal use; SQLite is used by tests.
- Binance public APIs: spot, USD-M futures, and Web3 endpoints are configured by the `BINANCE_*` settings.
- All 19 index charts use Yahoo Finance's free native chart feed for delayed intraday candles. US benchmarks and ICE DXY also use native daily OHLC; VIX retains Cboe's daily archive, while Chinese/Hong Kong indices prefer Tencent's free, paged daily archive with the existing long-history fallbacks (including pre-launch back series). `HSTECH.HK` is the verified Hang Seng TECH index identity. Index charts use points, localized names and ticker badges; ETF research pricing remains separate. Weekly/monthly candles aggregate daily observations; 30m uses 15m and 4h uses hourly observations with matching candle boundaries. The shared adapter validates index identity/period, limits HTTP connections to 3 and the response cache to 32 entries/32,000 candles, and persists confirmed intraday history. Conservative rolling history windows are 29 days (1m), 59 days (other minutes) and 729 days (hourly); delayed status and limits are displayed with the instrument. No paid feeds are configured.
- Crypto candles and Bitcoin technical indicators use native public REST endpoints. The supported exchange gateways are `binance`, `binanceusdm`, and `okx`; they reuse bounded connection pools without loading exchange-wide market tables. Chart candles share the existing history store with research and CLI readers. Failed upstream reads remain errors and are never cached as an empty history boundary.

## Fallbacks

Fetched and confirmed index intraday source periods are saved automatically, including watch-quote minutes and hourly input for 4h aggregation. Saved history is read across database rows and existing lossless archives after upstream rolling windows expire. Backward chart pagination uses candle counts rather than stopping at an empty calendar window. The 32,000-candle memory cache budget does not expire or truncate durable history. This is acquisition-time persistence; it does not run a new unattended full-market collector or recover never-saved expired data.

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
