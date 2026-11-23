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

## 策略历史模拟

| 文档 | 内容 |
| --- | --- |
| [Pine 策略测试器](CHART_WORKSPACE.md#策略测试器) | 脚本、时间区间、资金与费用、曲线和交易记录 |
| [Pine 编写规范](PINE_CODE_STANDARD.md) | 项目内 Pine 代码的编写与检查约定 |

Python 回测、参数扫描和研究诊断已退出页面、API、后台任务及 CLI，原实现保存在[归档目录](../archived/python_backtest_20261123/README.md)。研究记录、组合分析、信号复盘和数据检查的命令可通过 `python -m scripts.research_cli --help` 查询。

## 开发

- [贡献指南](../CONTRIBUTING.md)：开发环境、检查命令、生成契约与 PR 说明。
- [架构](ARCHITECTURE.md)：前后端分层、数据库、后台任务与运行边界。
- [界面规范](../DESIGN.md)：现有主题、字体、控件、响应式与键盘交互。
- [界面优化验收](verification/impeccable-workflows-20261029.md)：任务布局、操作路径、宽窄屏及错误恢复的本轮验证记录。
- [许可证范围](../LICENSING.md)与[第三方说明](../THIRD_PARTY_NOTICES.md)：源码、依赖和金融数据的使用条件。
