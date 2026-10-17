# Heimdall

Heimdall 是一个本地运行的加密货币市场研究与组合分析应用。它把行情、技术指标、市场信号、可配置的大模型分析和几种长期投资工具放在同一个 FastAPI + Vue 界面中。

它不会连接账户下单，也不保证收益。模型输出和历史回测类结果只能作为研究材料，不能替代个人判断。

## 当前功能

- 图表工作台：单图／双图／四图、手动画线、独立自选、内置指标、Pine 编辑与策略测试器
- 实时行情、EMA、MACD、RSI、ATR 和结构化市场分析
- 市场信号、Binance 合约市场与 Web3 排行
- 股票市场：按股票汇总 Binance、OKX、Bitget 的现货与永续合约支持标签，支持全量公开目录刷新、搜索及筛选（[覆盖范围](docs/EQUITY_CATALOG.md)）
- 币种对比、DCA 模拟、减半周期观察
- 研究清单、投资判断、研究笔记、价格与指标提醒，以及统一资产研究页
- 历史交易信号、结果评估、MFE/MAE 和分来源、分策略复盘（智能开单生成入口已下线）
- 可保存、运行和按历史快照回看的市场筛选器
- 多组合交易流水、成本与费用核算、TWR/MWR、基准对比、相关性和压力测试
- 可复现的 Markdown 研究报告，以及数据覆盖、时效和运行状态诊断
- 独立的 API 与后台运行进程，数据库心跳、即时首次采集和运行健康检查
- 设置页中的模型提供商和显示货币配置

组合数据保存在数据库中，不再依赖浏览器临时快照。多个窗口同时修改时会通过版本号拒绝覆盖；删除的组合可以在回收区恢复。

图表工作台使用说明、Pine 兼容边界和数据保存方式见 [图表工作台](docs/CHART_WORKSPACE.md)。

## 环境要求

当前项目只验收 Windows。

- Python 3.12.x
- Node.js 22.12.0 或更高版本
- npm
- PostgreSQL，或用于本地研究的 SQLite
- Redis 可选；不可用时应用会使用内存缓存

Python 依赖的可复现安装清单是 `requirements.lock`，前端依赖由 `frontend/package-lock.json` 固定。抽象依赖同时记录在 `pyproject.toml` 和 `requirements.txt` 中。

## 安装

在项目根目录执行：

```powershell
py -3.12 -m venv venv
.\venv\Scripts\python.exe -m pip install --require-hashes -r requirements.lock

Push-Location frontend
npm ci
Pop-Location
```

复制配置模板：

```powershell
Copy-Item .env.example .env
```

`DATABASE_URL` 是唯一数据库入口，必须显式配置。例如，把本地 SQLite 数据放到 D 盘：

```dotenv
DATABASE_URL=sqlite:///D:/Tools/HeimdallData/heimdall.db
```

正常长期运行建议使用 PostgreSQL：

```dotenv
DATABASE_URL=postgresql://user:password@localhost:5432/heimdall
```

模型 API Key、Redis 和运行目录等配置见 `.env.example`。Redis 未配置或不可用不会阻止启动；模型未配置时，相关接口会返回明确的不可用状态，不会伪造分析结果。

初始化或升级数据库：

```powershell
.\venv\Scripts\python.exe -m scripts.prepare_db
```

现有数据库会依次升级到研究追踪、组合流水、信号复盘、筛选器和报告所需的表结构。新增研究功能的操作口径、CLI 示例和历史结果限制见 `docs/RESEARCH_WORKFLOWS.md`。

## 启动

推荐使用 Windows 启动器：

```powershell
.\dev_start.bat
```

启动器会依次完成数据库迁移、API 存活检查、后台进程就绪检查，最后再启动前端。三个进程分别运行，避免网页可打开但定时采集没有工作的假就绪状态。

如果 `.env` 使用本机 PostgreSQL 且对应 Windows 服务尚未运行，启动器会只为“启动该服务”弹出一次 UAC 确认；应用的 API、后台进程和前端仍以当前普通用户运行。取消确认时，启动器会停止并明确显示需要手动启动的服务名，不会在数据库不可用时继续启动出一个假就绪页面。

默认地址：

- 前端：http://127.0.0.1:4173
- API：http://127.0.0.1:8000
- API 文档：http://127.0.0.1:8000/docs
- 存活检查：http://127.0.0.1:8000/health/live
- 完整就绪检查：http://127.0.0.1:8000/health

手动启动时也要保持三个终端：

```powershell
# 终端 1：API
$env:APP_RUNTIME_ROLE = "api"
.\venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# 终端 2：后台运行时
$env:APP_RUNTIME_ROLE = "background"
.\venv\Scripts\python.exe -m scripts.run_background_runtime

# 终端 3：前端
Push-Location frontend
npm run dev -- --host 127.0.0.1 --port 4173 --strictPort
```

构建后的 `frontend/dist` 会由 FastAPI 直接托管；开发期由 Vite 代理 API。

## 本地策略回测

在「研究 → 策略回测」运行单文件 Python 策略，支持多空、固定止盈止损、移动止损、逐笔图表复盘和快照重跑。在「研究 → 批量参数比较」填写多个取值或起止范围，软件自动组合、计算、排序并保留全部版本。外部 Agent 通过 `python -m scripts.research_cli backtest` / `sweep` 使用同一功能。参见[本地回测说明](docs/LOCAL_BACKTESTS.md)和[批量参数比较](docs/PARAMETER_SWEEPS.md)。请保持后台运行时启动，默认同时计算两组，相同输入复用行情。

## 验证

后端测试和语法检查：

```powershell
.\venv\Scripts\python.exe -m compileall -q app config scripts test utils
.\venv\Scripts\python.exe -m pytest -q
```

前端契约和构建：

```powershell
$env:HEIMDALL_PYTHON = (Resolve-Path .\venv\Scripts\python.exe)
npm run build:frontend
```

`npm run build:frontend` 会先从 FastAPI 路由和 Pydantic 模型重新生成 TypeScript 契约，再执行类型检查和 Vite 构建。以下生成文件不应手写：

- `frontend/src/api/errors.ts`
- `frontend/src/api/routes.ts`
- `frontend/src/modules/market/generatedContracts.ts`
- `frontend/src/modules/system/generatedContracts.ts`
- `frontend/src/modules/tools/generatedContracts.ts`

CI 在 `windows-latest` 上使用 Python 3.12.10 和 Node.js 22.23.0，依赖安装、测试、前端构建和契约漂移都是阻断项。

## 数据和运行文件

运行日志、临时文件、配置 JSON 和后台锁默认写入项目根目录的 `.heimdall_runtime`。可以通过 `RUNTIME_ROOT_DIR`、`LOG_DIR` 和 `TEMP_DIR` 把它们统一放到其他磁盘。

`data/btc_history_early.json` 含早期合成数据和后续交易所代理数据。精确日期边界、生成过程、文件哈希和适用限制见 `data/README.md`。DCA 页面会在结果涉及合成区间时显示数据质量警告。

外部数据源、可选降级路径和诊断命令见 `docs/DATA_SOURCES.md`。

## 研究 CLI

外部 Agent 或脚本可以直接调用稳定的命令行入口，不需要把 Agent 运行时嵌入应用。命令只向标准输出写一行结构化 JSON；成功时 `ok` 为 `true`，失败时以非零状态退出并把同一结构写到标准错误。

```powershell
.\venv\Scripts\python.exe -m scripts.research_cli health
.\venv\Scripts\python.exe -m scripts.research_cli asset BTC/USDT --timeframe 1h
.\venv\Scripts\python.exe -m scripts.research_cli signals evaluate
.\venv\Scripts\python.exe -m scripts.research_cli portfolio <组合ID> --benchmark BTC/USDT --shock BTC/USDT=-30
.\venv\Scripts\python.exe -m scripts.research_cli report generate --type daily_brief --title "每日研究简报"
```

完整命令和参数使用 `-h` 查看，工作流说明见 `docs/RESEARCH_WORKFLOWS.md`。

策略研究使用[统一研究入口](docs/STRATEGY_RESEARCH.md)：`catalog` 查旧证据，`study` 保存问题、冻结版本和验证顺序，`backtest` 复用结果、查询交易并检查参数影响。[本次会话复盘](docs/STRATEGY_RESEARCH_RETROSPECTIVE_20260912.md)记录了研究中走过的弯路与适用边界。

## 项目结构

```text
app/          FastAPI 入口、业务服务、领域模型、基础设施和 HTTP 契约
alembic/      数据库迁移
config/       应用配置
data/         随仓库提供的数据及来源说明
frontend/     Vue 3、Vite 和 TypeScript 前端
scripts/      可通过 python -m scripts.<name> 调用的命令
test/         后端与契约测试
archived/     保留的历史实现和过期项目材料，不属于当前运行入口
```

## 许可证

本项目采用 GNU Affero General Public License v3.0 or later。完整文本见 `LICENSE`，文件级边界和第三方材料见 `LICENSING.md` 与 `THIRD_PARTY_NOTICES.md`。
