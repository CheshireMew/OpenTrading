<!-- readme-header:start -->

<p align="center">
  <img src="./docs/assets/opentrading-logo.png" width="160" alt="OpenTrading">
</p>

<h1 align="center">OpenTrading</h1>

<p align="center">
  <strong>Market charts, strategy research, and portfolio analysis.</strong>
</p>

<p align="center">
  <a href="./README.md">中文</a> · <strong>English</strong> · <a href="./README.ja.md">日本語</a> | <a href="./docs/README.md">文档</a> | <a href="./CONTRIBUTING.md">贡献</a> | <a href="https://github.com/CheshireMew/OpenTrading/issues">反馈</a>
</p>

<p align="center">
  <a href="https://x.com/0xCheshire" title="X"><img src="https://img.shields.io/badge/X-%400xCheshire-000000?logo=x&amp;logoColor=white" alt="X：@0xCheshire"></a>
  <a href="https://t.me/CheshireBTC" title="Telegram"><img src="https://img.shields.io/badge/Telegram-CheshireBTC-26A5E4?logo=telegram&amp;logoColor=white" alt="Telegram：CheshireBTC"></a>
  <a href="https://blog.blacknico.com/" title="Blog"><img src="https://img.shields.io/badge/Blog-blog.blacknico.com-2E7D32?logo=rss&amp;logoColor=white" alt="博客：blog.blacknico.com"></a>
  <a href="https://blacknico.com/" title="Homepage"><img src="https://img.shields.io/badge/Home-blacknico.com-1F6FEB?logo=googlechrome&amp;logoColor=white" alt="个人主页：blacknico.com"></a>
</p>

<p align="center">
  <a href="https://github.com/CheshireMew/OpenTrading/stargazers"><img src="https://img.shields.io/github/stars/CheshireMew/OpenTrading?style=flat" alt="GitHub Stars"></a>
  <a href="https://github.com/CheshireMew/OpenTrading/forks"><img src="https://img.shields.io/github/forks/CheshireMew/OpenTrading?style=flat" alt="GitHub Forks"></a>
  <a href="https://github.com/CheshireMew/OpenTrading/blob/main/LICENSE"><img src="https://img.shields.io/github/license/CheshireMew/OpenTrading?style=flat" alt="Repository License"></a>
</p>

<!-- readme-header:end -->

Choose a symbol and timeframe, add indicators or Pine scripts, record portfolio trades, and review strategy results. Market coverage focuses on cryptocurrencies.

## Features

| Use case | What you can do |
| --- | --- |
| [Charting](docs/CHART_WORKSPACE.md) | One, two, or four charts, watchlists, drawing tools, technical indicators, a Pine editor, and a strategy tester |
| [Market monitoring](docs/DATA_SOURCES.md) | Market signals, Binance derivatives, Web3 rankings, and [equity-related instruments offered by exchanges](docs/EQUITY_CATALOG.md) |
| Investment tools | Asset comparison, DCA simulation, and Bitcoin halving cycles |
| [Portfolio analysis](docs/RESEARCH_WORKFLOWS.md) | Trade ledger, costs and fees, returns, benchmarks, correlations, and stress tests |
| [Strategy research](docs/LOCAL_BACKTESTS.md) | Python backtests, [parameter sweeps](docs/PARAMETER_SWEEPS.md), result review, and research reports |

## Install and run

**Windows** is the currently validated platform. Install Git, Python **3.12.x**, Node.js **≥ 22.12.0**, and npm. Open PowerShell in the directory where you want to keep the project:

```powershell
git clone https://github.com/CheshireMew/OpenTrading.git
cd OpenTrading
py -3.12 -m venv venv
.\venv\Scripts\python.exe -m pip install --require-hashes -r requirements.lock
npm --prefix frontend ci
Copy-Item .env.example .env
```

Set the database URL in `.env`. SQLite is a straightforward option for a first local setup:

```dotenv
DATABASE_URL=sqlite:///./.opentrading_runtime/opentrading.db
```

Start the application:

```powershell
.\dev_start.bat
```

The launcher prepares the database and starts the API, background tasks, and frontend. Once it reports that services are ready, open **[http://127.0.0.1:4173](http://127.0.0.1:4173)** to reach the chart workspace. Press `Q` or `Ctrl+C` to stop services.

Redis and model API keys are optional. See the [startup guide](docs/GETTING_STARTED.md) for PostgreSQL, manual startup, logs, and troubleshooting. Detailed documentation is currently in Chinese.

## Useful entry points

| Entry | Address or documentation |
| --- | --- |
| Chart workspace | `/` · [Usage and Pine compatibility](docs/CHART_WORKSPACE.md) |
| Portfolios | `/tools/portfolio-balance` |
| Data health | `/system/data-health` |
| API documentation | [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) |
| Python backtests and parameter sweeps | `/research/backtests` · `/research/parameter-sweeps` |

Research pages are currently hidden from the main menu. Visit their paths directly after startup, or use the research CLI:

```powershell
.\venv\Scripts\python.exe -m scripts.research_cli --help
.\venv\Scripts\python.exe -m scripts.research_cli asset BTC/USDT --timeframe 1h
```

The CLI returns structured JSON for scripts. See [research workflows](docs/RESEARCH_WORKFLOWS.md) and [strategy research](docs/STRATEGY_RESEARCH.md) for the full command reference.

## Data and backtest limitations

OpenTrading supports research and simulation; it does not connect trading accounts to place orders. Pine v5/v6 support is partial. Pine and Python backtests use different engines and cost assumptions, so check their respective documentation before comparing results.

Early Bitcoin history includes synthetic and proxy data; see [data/README.md](data/README.md) for sources and date boundaries. External market data can have gaps or delays. Historical results and model analysis do not predict future returns.

## Development and documentation

The frontend uses Vue 3, TypeScript, and Vite. The backend uses FastAPI, SQLAlchemy, and a separate background process. See [CONTRIBUTING.md](CONTRIBUTING.md) for development commands and contribution guidance, and the [documentation index](docs/README.md) for feature guides and architecture.

## License and acknowledgements

Original project code is licensed under [AGPL-3.0-or-later](LICENSE); see [LICENSING.md](LICENSING.md) for scope. Third-party dependencies and financial data retain their own terms, as described in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

The chart workspace uses [LuxAlgo Vela](https://luxalgo.com/vela), Vela-pinets, and [PineTS](https://github.com/alaa-eddine/PineTS). Development skills in `.agents/skills/` come from [emilkowalski/skills](https://github.com/emilkowalski/skills) under the [MIT License](.agents/skills/LICENSE).
