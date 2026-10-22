# 启动指南

先完成 [README 中的安装步骤](../README.md#安装与启动)。本页补充数据库选择、可选配置、手动启动和排障；命令均在项目根目录的 PowerShell 中执行。

## 数据库与可选配置

`DATABASE_URL` 必须显式填写在 `.env` 中。首次本地使用可以选择 SQLite，数据库目录会自动创建：

```dotenv
DATABASE_URL=sqlite:///./.opentrading_runtime/opentrading.db
```

已有 PostgreSQL 时，先创建数据库，再填写实际连接信息：

```dotenv
DATABASE_URL=postgresql://user:password@localhost:5432/opentrading
```

启动器会自动执行数据库准备和迁移。手动启动，或单独升级现有数据库时，运行：

```powershell
.\venv\Scripts\python.exe -m scripts.prepare_db
```

| 配置 | 作用 |
| --- | --- |
| `REDIS_HOST`、`REDIS_PORT` 等 | Redis 缓存；不可用时退回内存缓存，不阻止应用启动 |
| `DEEPSEEK_API_KEY` | 可选的模型分析；也可在应用设置页配置提供商 |
| `RUNTIME_ROOT_DIR` | 日志、临时文件和运行状态的根目录，默认 `.opentrading_runtime/` |
| `LOG_DIR`、`TEMP_DIR` | 分别覆盖日志与临时目录 |

完整变量见 [.env.example](../.env.example)。如需把运行数据放在其他磁盘，修改运行根目录；SQLite 数据库的位置仍由 `DATABASE_URL` 单独决定。

## Windows 启动器

```powershell
.\dev_start.bat
```

启动器在一个终端中汇总 API、后台任务与前端日志。API 存活后会启动其余组件，等待首次采集与行情连接完成后显示完整就绪状态。完整日志位于 `.opentrading_runtime/launcher/`；覆盖运行根目录时随之迁移。

按 `Q` 或 `Ctrl+C` 停止本次启动的服务。也可以在另一个终端执行：

```powershell
.\dev_start.bat --stop
```

已有 Redis 实例会被复用；如果本机安装了 Redis，启动器可通过 PATH 或 `OPENTRADING_REDIS_EXE` 找到它并启动临时实例。未安装时不会自动下载，应用使用内存缓存。

连接本机 PostgreSQL 而对应 Windows 服务未启动时，启动器可能请求一次 UAC 确认，仅用于启动该服务。应用进程仍以当前用户运行；也可以事先手动启动 PostgreSQL 服务。

## 地址与健康检查

| 用途 | 默认地址 |
| --- | --- |
| 前端 | [http://127.0.0.1:4173](http://127.0.0.1:4173) |
| API 文档 | [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) |
| API 存活 | [http://127.0.0.1:8000/health/live](http://127.0.0.1:8000/health/live) |
| 完整就绪 | [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health) |

使用启动器时，访问 `8000` 上的网页会转到 `4173` 的开发界面，API 与文档仍由 `8000` 提供。独立运行 FastAPI 且未设置 `OPENTRADING_FRONTEND_DEV_URL` 时，会托管已有的 `frontend/dist`。

## 手动启动

先准备数据库，再分别打开三个终端，并让它们都停留在项目根目录。

终端 1：API。

```powershell
$env:APP_RUNTIME_ROLE = "api"
.\venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

终端 2：后台任务。

```powershell
$env:APP_RUNTIME_ROLE = "background"
.\venv\Scripts\python.exe -m scripts.run_background_runtime
```

终端 3：前端。

```powershell
npm --prefix frontend run dev -- --host 127.0.0.1 --port 4173 --strictPort
```

浏览器访问 `4173`，Vite 会代理 API 请求。手动运行时需分别停止三个终端中的进程。

## 常见问题

| 现象 | 检查方式 |
| --- | --- |
| 数据库连接失败 | 检查 `.env` 的 `DATABASE_URL`；PostgreSQL 需确认服务、数据库和账号均可用 |
| 启动期间 `/health` 返回 503 | 首次采集和后台心跳尚未完成时属于等待状态；持续失败时检查启动器日志和数据源连接 |
| 端口被占用或重复启动 | 优先回到已有启动窗口；需重启时先停止原启动器，再重新运行 |
| 页面内容像旧版本 | 使用 `4173` 的开发地址；手动 API 可能仍在托管之前构建的 `frontend/dist` |
| 回测一直排队 | 确认后台进程已启动，API 不会代替它执行研究任务 |
| 模型分析不可用 | 在设置页检查提供商和 API Key；行情图表不依赖模型配置 |
| 行情缺失或更新缓慢 | 查看 `/system/data-health` 和[数据源说明](DATA_SOURCES.md)，区分上游缺口与本地运行问题 |

开发检查与契约生成命令见[贡献指南](../CONTRIBUTING.md)。
