# Heimdall

Heimdall 是一个本地运行的加密货币市场研究与组合分析应用。它把行情、技术指标、市场信号、可配置的大模型分析和几种长期投资工具放在同一个 FastAPI + Vue 界面中。

它不会连接账户下单，也不保证收益。模型输出和历史回测类结果只能作为研究材料，不能替代个人判断。

## 当前功能

- 实时行情、EMA、MACD、RSI、ATR 和结构化模型分析
- 市场信号、Binance 合约市场与 Web3 排行
- 币种对比、DCA 模拟、减半周期观察
- 多组合配置、服务端持久化、软删除恢复、JSON 导入与导出
- 独立的 API 与后台运行进程，数据库心跳、即时首次采集和运行健康检查
- 设置页中的模型提供商、FRED 和显示货币配置

组合数据保存在数据库中，不再依赖浏览器临时快照。多个窗口同时修改时会通过版本号拒绝覆盖；删除的组合可以在回收区恢复。

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

模型 API Key、FRED、Redis 和运行目录等配置见 `.env.example`。Redis 未配置或不可用不会阻止启动；模型未配置时，相关接口会返回明确的不可用状态，不会伪造分析结果。

初始化或升级数据库：

```powershell
.\venv\Scripts\python.exe -m scripts.prepare_db
```

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
