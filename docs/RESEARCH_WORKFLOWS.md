# 研究工作流

策略实验请先使用[策略研究入口](STRATEGY_RESEARCH.md)：查询已有证据、冻结问题与参数、复用回测、记录每个问题的结论。此入口专门管理策略实验过程。

OpenTrading 的研究功能围绕“记录判断、保存当时证据、等待结果、回头校准”组织。所有可编辑记录都保存在数据库中；修改、归档和恢复使用版本号，避免多个窗口把较新的内容静默覆盖。

## 研究追踪

“研究追踪”页面可以创建研究清单，并为每个标的保存投资判断、目标价、失效价、标签和来源上下文。研究笔记分为判断、更新、复盘和决策四类，每条笔记可以保留创建时的结构化快照。Dashboard、Binance 行情和 Web3 排行中的标的可以直接加入研究清单。

提醒支持价格和页面已提供的指标字段，比较方式包括大于、大于等于、小于、小于等于、向上穿越、向下穿越、区间内和区间外。提醒带冷却时间，可写入应用内事件；选择 Windows 通知时，前端会在获得通知权限后，在应用打开期间每 15 秒轮询新事件，只投递明确配置 `windows` 渠道的事件，并保存已投递 ID 避免重复弹窗。后台运行时会周期检查提醒，也可以在页面、API 或 CLI 中手动触发。

统一资产页路径为 `/research/assets/<symbol>`。它汇总当前价格、历史 K 线、指标、突破监控和排行位置、90 天基准对比、研究判断、笔记、提醒、事件和历史交易信号。Web3 标的还包含热度排名、动态行情、合约审计与 Web3 K 线。某个数据源不可用时，页面保留其它可用内容，并在 `issues` 中明确列出缺口。

## 组合流水与风险

组合页现在以流水作为成本和损益的事实来源。支持入金、出金、买入、卖出、手续费、转入和转出，并支持编辑、归档、恢复、JSON/CSV 导入与导出。导入前会完成字段校验；现有组合记录不会因为导入失败而被清空。

核算采用移动平均成本。组合摘要包含现金、持仓市值、已实现损益、未实现损益、累计费用、总损益、简单收益率和 MWR/XIRR。风险面板根据能够取得的日线历史计算 TWR、基准及超额收益、年化波动率、最大回撤、95% 参数法 VaR、相关性矩阵、风险贡献、HHI、有效持仓数和最大单项权重。

压力测试包括历史共同最差交易日、全市场下跌 25%，以及用户提供的逐标的自定义冲击。缺少历史价格或共同交易日不足时，相应指标返回空值并写入问题说明，不用估算值冒充真实结果。

## 信号复盘

市场分析产生的交易信号会连同入场价、目标价、止损价、置信度、策略、理由、当时行情和指标快照自动保存。后台运行时会补充 1 小时、4 小时、24 小时和 7 天前瞻收益，并计算最大有利波动 MFE 和最大不利波动 MAE。

如果同一根 K 线同时触及目标价和止损价，结果标记为 `ambiguous`，不会擅自假定先后顺序。结果可按来源和策略统计，并按 0–39、40–59、60–79、80–100 置信度分桶对比期望胜率与实际胜率；过期但未命中目标或止损的信号标记为 `expired`。信号记录可以归档和恢复，原始生成快照不会被后续行情覆盖。

## 市场筛选器

筛选器可以保存现货、U 本位合约或两者的筛选条件，包括计价资产、24 小时涨跌幅、成交额、资金费率、突破评分、1 小时持仓量变化、1 小时 RSI、标的白名单和结果上限。也可把 Web3 热度排行加入筛选，按链和智能资金风险等级限制结果。每次实际运行都会把当时条件和结果保存为不可变快照。

历史回看不是使用今天的数据重新计算过去，而是返回所选时间点之前最近一次已保存的运行结果，并把 `historicalReplay` 标为 `true`。因此只有实际运行并保存过的时点可以回看；所选时间之前没有快照时会返回明确错误。

## 报告与数据健康

研究报告支持日报、周报、资产复盘、组合复盘和决策复盘。它从生成当时的研究记录、本期清单变更、已触发提醒、信号统计与置信度校准、可选资产或组合流水及风险分析，以及数据健康状态确定性生成 Markdown，同时保存完整结构化 `dataSnapshot`。页面可以导出 Markdown 或 JSON。已生成报告不会随着后续行情自动改写，因此可以用于复盘当时依据。

“数据健康”页面显示数据库迁移版本、K 线和指标覆盖起止、可计算序列的真实缺口数、持久化研究序列、后台组件的最近成功、失败与下次运行时间、当前缓存后端，以及 Binance 实时快照。可执行的修复动作包括校验数据库、强制刷新 Binance 快照、补齐某个标的历史、立即检查提醒和立即评估交易信号。Redis 不可用时应用按既有设计降级为进程内缓存，并在数据健康中显示当前后端、本地条目数和字节数。

## CLI

入口为：

```powershell
.\venv\Scripts\python.exe -m scripts.research_cli -h
```

常用调用：

```powershell
# 查看数据覆盖和运行状态
.\venv\Scripts\python.exe -m scripts.research_cli health

# 强制刷新实时市场快照
.\venv\Scripts\python.exe -m scripts.research_cli health --repair refresh_binance_snapshot

# 补齐某个标的最近一年的历史
.\venv\Scripts\python.exe -m scripts.research_cli health --repair hydrate_symbol_history --symbol BTC/USDT --days 365

# 获取统一资产研究快照
.\venv\Scripts\python.exe -m scripts.research_cli asset BTC/USDT --timeframe 1h --history-days 365

# 查询或立即评估已保存信号
.\venv\Scripts\python.exe -m scripts.research_cli signals list --symbol BTC/USDT --limit 50
.\venv\Scripts\python.exe -m scripts.research_cli signals evaluate

# 运行筛选器；as-of 返回该时间之前最近的保存结果
.\venv\Scripts\python.exe -m scripts.research_cli screener <筛选器ID>
.\venv\Scripts\python.exe -m scripts.research_cli screener <筛选器ID> --as-of 2026-08-24T12:00:00+08:00

# 计算组合风险，冲击值使用百分数
.\venv\Scripts\python.exe -m scripts.research_cli portfolio <组合ID> --period-days 365 --benchmark BTC/USDT --shock BTC/USDT=-30

# 生成并保存报告
.\venv\Scripts\python.exe -m scripts.research_cli report generate --type asset_review --symbol BTC/USDT --title "BTC 研究复盘"
.\venv\Scripts\python.exe -m scripts.research_cli report generate --type weekly_brief --portfolio-id <组合ID> --title "每周研究简报"
```

成功输出格式固定为：

```json
{"schemaVersion":1,"ok":true,"command":"health","data":{}}
```

失败时 `ok` 为 `false`，`error` 包含异常类型和可读消息，进程退出码为 1。调用方应该判断退出码和 `ok`，不要依赖自然语言消息解析结果。

## 数据与方法边界

- 价格、指标、资金费率和持仓量取决于上游数据源及本地已保存覆盖范围。界面和报告会显示缺口，不对缺失区间做无依据填充。
- 信号命中判断使用已取得 K 线的高低价；同根 K 线无法确定目标与止损的先后顺序。
- TWR、相关性、波动率、回撤和压力测试只使用拥有共同日期的历史数据。样本不足时返回空值。
- MWR 使用流水现金流求解 XIRR；现金流不具备有效正负结构时不返回结果。
- 报告和筛选器历史结果都是已保存快照，不是可重复获得的外部实时数据承诺。
# 结果查询与复盘

先使用研究结果目录查找已有参数和区间；连续账户诊断、单笔过程和两版交易差异也可直接读取保存结果。页面与 CLI 用法见 [研究结果目录与诊断](RESEARCH_RESULTS.md)。
