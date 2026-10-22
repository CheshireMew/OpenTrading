<!-- readme-header:start -->

<p align="center">
  <img src="./docs/assets/opentrading-logo.png" width="160" alt="OpenTrading">
</p>

<h1 align="center">OpenTrading</h1>

<p align="center">
  <strong>行情图表、策略研究与投资组合分析工具。</strong>
</p>

<p align="center">
  <strong>中文</strong> · <a href="./README.en.md">English</a> · <a href="./README.ja.md">日本語</a> | <a href="./docs/README.md">文档</a> | <a href="./CONTRIBUTING.md">贡献</a> | <a href="https://github.com/CheshireMew/OpenTrading/issues">反馈</a>
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

打开首页即可选择交易对与周期、添加指标或 Pine 脚本，也可以记录组合交易、比较资产和回看策略结果。行情以加密货币为主。

## 功能

| 场景 | 可以做什么 |
| --- | --- |
| [看盘](docs/CHART_WORKSPACE.md) | 单图、双图或四图，自选列表、绘图、技术指标、Pine 编辑器与策略测试器 |
| [市场观察](docs/DATA_SOURCES.md) | 市场信号、Binance 合约市场、Web3 排行，以及交易所支持的[股票相关品种](docs/EQUITY_CATALOG.md) |
| 投资工具 | 币种对比、DCA 模拟、比特币减半周期观察 |
| [组合分析](docs/RESEARCH_WORKFLOWS.md) | 交易流水、成本与费用、收益率、基准对比、相关性和压力测试 |
| [策略研究](docs/LOCAL_BACKTESTS.md) | Python 策略回测、[批量参数比较](docs/PARAMETER_SWEEPS.md)、结果复盘和研究报告 |

## 安装与启动

当前验收平台为 **Windows**。需要 Git、Python **3.12.x**、Node.js **≥ 22.12.0** 和 npm。在准备存放项目的目录打开 PowerShell：

```powershell
git clone https://github.com/CheshireMew/OpenTrading.git
cd OpenTrading
py -3.12 -m venv venv
.\venv\Scripts\python.exe -m pip install --require-hashes -r requirements.lock
npm --prefix frontend ci
Copy-Item .env.example .env
```

在 `.env` 中填写数据库地址。首次本地使用可以选择 SQLite：

```dotenv
DATABASE_URL=sqlite:///./.opentrading_runtime/opentrading.db
```

然后启动：

```powershell
.\dev_start.bat
```

启动器会准备数据库，并启动 API、后台任务与前端。显示服务就绪后，打开 **[http://127.0.0.1:4173](http://127.0.0.1:4173)**，首页即为图表工作台。按 `Q` 或 `Ctrl+C` 停止服务。

Redis 和模型 API Key 均为可选项。PostgreSQL、手动启动、日志位置及排障见[启动指南](docs/GETTING_STARTED.md)。

## 常用入口

| 入口 | 地址或文档 |
| --- | --- |
| 图表工作台 | `/` · [操作与 Pine 兼容范围](docs/CHART_WORKSPACE.md) |
| 组合 | `/tools/portfolio-balance` |
| 数据健康 | `/system/data-health` |
| API 文档 | [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) |
| Python 回测与参数比较 | `/research/backtests` · `/research/parameter-sweeps` |

研究页面目前未显示在主菜单中，启动后可直接访问对应路径，或使用研究 CLI：

```powershell
.\venv\Scripts\python.exe -m scripts.research_cli --help
.\venv\Scripts\python.exe -m scripts.research_cli asset BTC/USDT --timeframe 1h
```

CLI 返回结构化 JSON，适合脚本调用。完整命令见[研究工作流](docs/RESEARCH_WORKFLOWS.md)与[策略研究](docs/STRATEGY_RESEARCH.md)。

## 数据与回测边界

OpenTrading 用于研究与模拟，不连接交易账户下单。Pine 支持 v5/v6 的部分能力；Pine 与 Python 回测使用不同的引擎和费用口径，比较结果前请查看各自说明。

早期比特币历史包含合成与代理数据，来源及日期边界见 [data/README.md](data/README.md)。外部行情可能存在缺口或延迟，历史结果和模型分析不代表未来收益。

## 开发与文档

前端使用 Vue 3、TypeScript 和 Vite，后端使用 FastAPI、SQLAlchemy 和独立后台进程。开发命令与提交约定见[贡献指南](CONTRIBUTING.md)，功能说明和架构入口见[文档目录](docs/README.md)。

## 许可证与致谢

项目原创代码采用 [AGPL-3.0-or-later](LICENSE)，具体范围见 [LICENSING.md](LICENSING.md)。第三方依赖与金融数据保留各自的许可和使用条件，参见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

图表工作台使用 [LuxAlgo Vela](https://luxalgo.com/vela)、Vela-pinets 与 [PineTS](https://github.com/alaa-eddine/PineTS)。`.agents/skills/` 中的开发技能来自 [emilkowalski/skills](https://github.com/emilkowalski/skills)，采用 [MIT 许可证](.agents/skills/LICENSE)。
