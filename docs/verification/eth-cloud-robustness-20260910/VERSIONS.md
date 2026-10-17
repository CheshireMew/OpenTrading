# 策略副本与恢复记录

本轮已结束，停止在这批历史数据上扩展参数。结论和全部成绩见 [REPORT.md](REPORT.md)，固定计划见 [plan.json](plan.json)，逐次事先选参记录是 `q1-choice.json` 至 `q4-choice.json`。20 个正式回测的标识在 [project-runs.json](project-runs.json)。

| 检查点 | 保存内容 |
| --- | --- |
| `001-before-new-tests` | 开始新研究前的 32 个文件，含旧策略、引擎、参数、结果和报告 |
| `002-frozen-round-v1` | 执行本轮前锁定的策略 v1、测试程序、计划、依赖脚本和测试 |
| `003-before-checkpoint-validation` | 改进副本工具前的源码；修正为遇到缺失文件立即报错，避免误以为已备份 |
| `004-before-final-report-records` | 首次报告和发布工具，更新最终验证状态前的副本 |
| `005-before-readable-run-labels` | 给项目记录补充参数说明、修正图表空标题前的界面源码 |
| `006-before-run-interval-unit` | 将入场间隔显示为 K 线根数前的界面源码，避免把其他周期也当成十五分钟 |
| `007-completed-round-v1` | 完成本轮后的策略、程序、界面、参数、结果、正式记录和核对文件 |

每个目录都按项目相对路径保存可直接读取的文件，并带 `manifest.json` 校验清单。`versions/history.jsonl` 只追加；相同版本名不能重复使用。旧策略文件仍在 `strategies/`，没有被新策略覆盖。

本轮新策略是 `strategies/trend_cloud_robustness_v1.py`。旧利润保护策略仍是 `strategies/trend_cloud_profit_protection.py`，更早的 `trend_cloud_experiments.py`、`trend_cloud_comparison.py` 也均保留。查原始回测时，在项目里打开记录，使用“参数、数据来源与版本”查看当时配置，或用“按快照重跑”复现。研究页的新记录已直接显示中心周期、宽度、门槛、保护和过滤参数。

以后修改前，在项目目录使用以下命令保存当前文件；文件路径可以继续列出多个。不存在的文件会报错，不会跳过。运行使用项目的 `venv/Scripts/python.exe`。

```powershell
.\venv\Scripts\python.exe -m scripts.cloud_strategy_versions 008-before-next-change strategies/trend_cloud_robustness_v1.py
```

需要新策略时，另存新文件，例如 `trend_cloud_robustness_v2.py`，并将文件内 `STRATEGY.id` 同步改成新文件名（不含 `.py`）；不要覆盖 v1。新研究使用新结果目录，保留失败结果。单纯把旧参数改成新参数重跑，会生成独立正式记录，不会修改原回测。

完整逐笔数据保存在项目的 `.heimdall_runtime/cloud-robustness-20260910/`。每次模拟的文件均记录具体参数、日期和源码校验值；20 个正式回测另有独立的策略、配置、行情快照和结果。引擎本轮未改，仍为 v4；三组旧基准已核对逐笔交易及账户曲线完全一致。
