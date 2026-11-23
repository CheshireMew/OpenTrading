# Python 回测与策略研究归档

后续变更：用户同日要求组合平衡、研究报告与组合偏离也退出，并明确要求删除所有已退出功能的数据库记录。迁移 `024_retire_legacy_tools` 已移除旧 Python 回测表；下文关于保留历史表的说明仅记录最初归档时的安排，当前以[后续清理说明](../portfolio_balance_20261123/README.md)为准。

2026-11-23 按用户确认退出独立 Python 策略回测、参数扫描和深入研究诊断。策略历史模拟统一保留图表工作台的 Pine/PineTS 策略测试器，定投与组合分析继续运行。

归档包含旧引擎及策略、参数扫描与研究结果服务、专用 API 和 CLI、页面及组件、研究脚本、专用测试和旧使用说明。原相对路径保留，源码加 `.txt` 后缀，不参加导入、测试发现和前端构建。`manifest.json` 记录逐文件 SHA-256；标记 `snapshot` 的混合测试文件只归档原文，活动版本继续保留非回测测试。

应用不再注册 `/research/backtests`、`/research/parameter-sweeps`、`/research/results` 页面，或 `/api/v1/local-backtests`、`/api/v1/parameter-sweeps`、`/api/v1/research-results` 接口。研究 CLI 不再提供 `backtest`、`sweep`、`study`、`catalog` 命令；后台不再启动 Python 回测队列，API 启动也不再重建旧研究结果索引。旧 Python 策略生成与快照 CI 检查同步退出。

数据库迁移历史以及历史回测表保留，用于保存已有记录与兼容数据库结构；不再有活动回测写入入口。历史研究材料和运行文件保持原位，包括 `docs/verification` 与运行目录下已有材料。本次不删除行情、压缩行情归档、用户 Pine 脚本、Pine 结果、定投或组合数据。图表工作台仍使用共享的文件锁工具，因此 `app/infra/research_files.py` 作为公共基础工具继续保留。

这里的旧命令和原路径只作历史参考，不表示当前版本仍支持。若将来明确恢复功能，需要重新接入和验证，不要直接从本目录导入代码。
