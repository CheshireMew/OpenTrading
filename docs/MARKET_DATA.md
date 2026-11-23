# 美元流动性与历史数据命令

OpenTrading 的「美元流动性」位于 `/indicators/market-data`。页面展示由 FRED 和美国财政部公开数据计算的压力分位、历史曲线、变化驱动和分组指标。后台进程默认每四小时刷新一次，页面也支持手动刷新。跨资产历史数据可通过命令行查询。

## 命令行

在 OpenTrading 目录下使用同一 Python 环境运行 `python -m scripts.market_data_cli`。行情与流动性代码已并入主项目的领域、数据源、存储和服务层，CLI、API 与后台使用同一份应用配置和数据库。标准日线合同仍为 `signal-lab.history.v1`，保持已有调用和历史快照兼容；标准输出为一个 JSON 文档。完整历史存为 Parquet，结果中的 `status` 和 `coverage.complete` 表明覆盖情况。

```powershell
.\venv\Scripts\python.exe -m scripts.market_data_cli instruments resolve "贵州茅台"
.\venv\Scripts\python.exe -m scripts.market_data_cli prices history --instrument 600519.SH --period 5y
.\venv\Scripts\python.exe -m scripts.market_data_cli prices history --instrument AAPL.US --period 6mo --basis both --cache-only
.\venv\Scripts\python.exe -m scripts.market_data_cli prices point --instrument SPY.US --date 2024-06-30
.\venv\Scripts\python.exe -m scripts.market_data_cli prices compare --instrument SPY.US --instrument QQQ.US --period 5y
.\venv\Scripts\python.exe -m scripts.market_data_cli prices verify --instrument 00700.HK --period 5y
.\venv\Scripts\python.exe -m scripts.market_data_cli macro history --series FRED:DGS10 --period 5y
```

`prices update` 用于增量更新。`prices snapshots` 可以导出、检查和导入离线快照。`prices datasets build` 支持批量构建分区数据集，`prices indicators materialize` 保存版本化技术指标产物。`instruments classifications` 支持导入和查询按日期生效的分类。`data liquidity-sync` 和 `jobs status` 可在命令行刷新和检查流动性数据。

## 从 Signal Lab 导入

结构化数据使用主项目的 `DATABASE_URL`。原始接口响应和 Parquet 文件默认继续保存在 `RUNTIME_ROOT_DIR/signal-lab`，以沿用已有数据；可用 `MARKET_DATA_DIR` 指定文件位置。旧的 `SIGNAL_LAB_DATA_DIR` 和存储配额变量仍作为配置别名支持，新变量优先。公开流动性数据无需密钥，Tiingo 和带密钥的 FRED 数据入口可分别配置 `TIINGO_API_TOKEN` 和 `FRED_API_KEY`。

首次导入先运行数据库迁移，再检查源目录和预计导入内容。应在启动 OpenTrading 后台进程前完成首次导入，以便沿用既有的流动性任务。

```powershell
.\venv\Scripts\python.exe -m scripts.prepare_db
.\venv\Scripts\python.exe -m scripts.market_data_cli migrate --source E:\Code\signal-lab\.data
.\venv\Scripts\python.exe -m scripts.market_data_cli migrate --source E:\Code\signal-lab\.data --apply
```

导入范围为市场数据、宏观历史、流动性和对应的任务记录。原项目保存配置回测、研究记录及相关产物。导入会检查源架构、关联记录、产物和目标库状态，记录写入在单个数据库事务内完成。同一份源数据可重复执行校验。

## K 线在线存储与历史归档

`klines` 是全站共享行情，同一品种、周期、时间只存一份。超过 `KLINE_RETENTION_DAYS`（默认 365 天）的分钟和小时行情，会先写成 Zstandard 压缩 Parquet，逐值读回核对价格、成交量及 `finalized` 状态，再在同一个数据库事务内登记文件并移出在线表。包含 30 分钟及 Web3 的 `15min` 周期；日线、周线、月线继续在线保留。后台启动时即安排归档，之后每 24 小时执行；中断后可以重复执行。

归档默认位于 `RUNTIME_ROOT_DIR/market_archive`，可用 `KLINE_ARCHIVE_DIR` 指定。SQLite 开发／测试库默认使用数据库文件旁的独立归档目录，避免混用不同数据库的文件。文件按内容摘要命名且不覆盖原始内容，数据库中的相对路径允许整个归档目录搬迁。备份、迁移和恢复必须同时保存数据库和这个目录；更改配置本身不会搬迁文件。

历史查询自动合并在线数据和归档，较新的行情修正优先。同一条已收盘行情内容没有变化时，不重复更新数据库。文件缺失或摘要错误会明确报错，不能按“空历史”处理。数据健康页面也计入已归档的确认行情。

连续交易的普通加密货币交易对支持用完整、已确认的小周期合成较大周期，范围为分钟、小时、UTC 日线、周一开始的周线及自然月线。只有每根子 K 线齐全、开盘时间对齐时才生成开高低收及成交量；月线按实际日历处理，包括闰年二月。已有原始大周期优先。与合成值逐值一致的新大周期不再重复存储，有不同舍入或成交量的原始值仍保留。股票和指数不套用连续交易市场的时间规则；旧的未确认缓存也不会仅因时间过去而自动变成已确认数据。

以下命令不需要重新下载行情。修改操作默认只显示计划，显式加 `--apply` 后才执行；恢复保留原始确认状态，已有在线修正优先，归档文件继续保留。

```powershell
.\venv\Scripts\python.exe -m scripts.prepare_db
.\venv\Scripts\python.exe -m scripts.market_storage status
New-Item -ItemType Directory -Path .opentrading_runtime/market-storage -Force | Out-Null
.\venv\Scripts\python.exe -m scripts.market_storage fingerprint | Set-Content -Encoding utf8 .opentrading_runtime/market-storage/original-history.json
.\venv\Scripts\python.exe -m scripts.market_storage archive --apply
.\venv\Scripts\python.exe -m scripts.market_storage verify --baseline .opentrading_runtime/market-storage/original-history.json
.\venv\Scripts\python.exe -m scripts.market_storage restore --apply
```

`verify --baseline` 比较归档前后的全部原始行、浮点数与确认状态，按月分批核对。`restore` 只在需要把冷数据放回在线表时运行，正常查询无需恢复。归档完成且验证通过后，可在维护窗口运行 `python -m scripts.market_storage compact --apply`，整理 PostgreSQL 的 K 线表及其索引，把空闲空间归还磁盘；该命令会先验证归档，整理期间会锁住 K 线表。服务器只有明确执行部署或维护时才应用这些变更。
