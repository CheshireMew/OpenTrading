# OpenTrading 文档

第一次使用请从[安装与启动](../README.md#安装与启动)开始。以下文档按使用任务组织。

## 使用

| 文档 | 内容 |
| --- | --- |
| [启动指南](GETTING_STARTED.md) | 数据库、可选配置、手动启动与常见故障 |
| [图表工作台](CHART_WORKSPACE.md) | 布局、自选、绘图、Pine 编辑器、策略测试器与兼容范围 |
| [数据源](DATA_SOURCES.md) | 行情来源、降级路径和数据诊断 |
| [股票相关品种](EQUITY_CATALOG.md) | Binance、OKX、Bitget 的目录覆盖与支持标签 |
| [研究工作流](RESEARCH_WORKFLOWS.md) | 研究记录、组合、信号复盘、筛选器、报告与 CLI |
| [历史数据来源](../data/README.md) | 早期比特币数据的生成方式、日期边界和使用限制 |

## 策略研究

| 文档 | 内容 |
| --- | --- |
| [本地 Python 回测](LOCAL_BACKTESTS.md) | 策略输入、执行口径、行情快照和逐笔复盘 |
| [批量参数比较](PARAMETER_SWEEPS.md) | 参数组合、后台计算与结果排序 |
| [策略研究](STRATEGY_RESEARCH.md) | 查询已有证据、冻结问题与版本、安排验证顺序 |
| [研究结果](RESEARCH_RESULTS.md) | 结果目录与研究记录 |
| [Pine 编写规范](PINE_CODE_STANDARD.md) | 项目内 Pine 代码的编写与检查约定 |

研究页面当前未出现在主菜单中。启动应用后可直接打开 `/research/backtests`、`/research/parameter-sweeps` 等路径，也可使用 `python -m scripts.research_cli --help` 查找 CLI 命令。

## 开发

- [贡献指南](../CONTRIBUTING.md)：开发环境、检查命令、生成契约与 PR 说明。
- [架构](ARCHITECTURE.md)：前后端分层、数据库、后台任务与运行边界。
- [许可证范围](../LICENSING.md)与[第三方说明](../THIRD_PARTY_NOTICES.md)：源码、依赖和金融数据的使用条件。
