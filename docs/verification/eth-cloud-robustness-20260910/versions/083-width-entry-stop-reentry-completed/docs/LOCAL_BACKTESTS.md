# 本地策略回测

多版本策略研究请使用[统一研究 CLI](STRATEGY_RESEARCH.md)，先查已有结果，再冻结问题、参数和验证范围。`backtest result` 默认返回摘要；需要旧版完整输出时显式使用 `--full`，大文件优先导出到本地。

Heimdall 使用自己的逐根 K 线引擎进行单币种多空研究。结果含义统一为：**基于所选价格数据、不计成本的多空策略模拟**。使用现有交易所目录中的现货历史，不需要 Freqtrade 或 TradingView 会员。

## 使用入口

先按项目 README 启动数据库、API、后台运行时和前端。升级已有数据库时执行 `python -m scripts.prepare_db`，本功能对应迁移 `018`。Windows 请使用项目 `venv\Scripts\python.exe`。后台不运行时任务会保留在队列中，API 不会代替后台执行回测。

页面位于「研究 → 策略回测」(`/research/backtests`)。选择策略、参数、交易对、周期和 UTC 区间后提交。结束时间不包含在区间内，起止必须对齐周期；例如一月小时线填写 `2025-01-01 00:00` 至 `2025-02-01 00:00`。刷新页面保留当前任务。点击逐笔交易可定位附近 K 线及该笔止损、止盈轨迹，长持仓使用 K 线翻页继续查看。

命令行调用同一个应用服务，标准输出沿用研究 CLI 的 JSON 协议，失败退出码非零。以下命令在项目根目录运行：

```powershell
.\venv\Scripts\python.exe -m scripts.research_cli backtest strategies
.\venv\Scripts\python.exe -m scripts.research_cli backtest run --strategy ma_cross --symbol BTC/USDT --timeframe 1h --start 2025-01-01T00:00:00Z --end 2025-04-01T00:00:00Z --initial-cash 10000 --position-pct 100 --wait
.\venv\Scripts\python.exe -m scripts.research_cli backtest list
.\venv\Scripts\python.exe -m scripts.research_cli backtest status RUN_ID
.\venv\Scripts\python.exe -m scripts.research_cli backtest result RUN_ID
.\venv\Scripts\python.exe -m scripts.research_cli backtest cancel RUN_ID
.\venv\Scripts\python.exe -m scripts.research_cli backtest rerun RUN_ID --wait
.\venv\Scripts\python.exe -m scripts.research_cli backtest archive RUN_ID
.\venv\Scripts\python.exe -m scripts.research_cli backtest export RUN_ID --format trades --output D:\Code\Heimdall\.heimdall_runtime\trades.csv
```

`run` 不加 `--wait` 时返回已入队任务。参数文件通过 `--parameters D:\path\parameters.json` 传入 JSON 对象，例如 `{"fast":10,"slow":30,"stop":5,"target":10,"trailing":0}`。`export --format` 支持 `json`、`trades`、`equity`，文件必须不存在，避免意外覆盖。`list --archived` 查看归档记录。状态查询可查看失败任务；`result` 或 `--wait` 遇到未成功完成的任务会以非零退出码返回。

## 外部 Agent 的策略接口

在根目录 `strategies/` 新建单个 UTF-8 Python 文件，文件名与 `STRATEGY.id` 相同，只使用字母、数字、下划线和连字符。可从 `strategies/ma_cross.py` 复制。页面刷新会重新读取策略目录；已经创建的任务使用已保存源码。

```python
from app.domain.local_backtest import Intent

STRATEGY = {
    "id": "my_strategy",
    "name": "示例动量",
    "description": "收盘上涨开多，下跌平仓",
    "api_version": "1",
    "warmup_bars": 1,
    "parameters": {
        "stop": {"type": "float", "default": 5, "min": 0.1, "max": 50,
                 "label": "止损 %"},
    },
}

def on_bar(context):
    previous, current = context.history[-2:]
    if current.close > previous.close:
        return Intent("long", stop_loss_pct=context.parameters["stop"], reason="收盘上涨")
    return Intent("close", reason="收盘未上涨")
```

元数据必须是静态字典或常量形式的 `dict(...)`，不能通过函数调用生成。接口会在 API 进程内静态读取元数据，策略代码仅在独立计算子进程中执行。参数类型为 `int`、`float`、`bool`、`str`；数值可设 `min/max`。未知参数、类型错误及越界会直接报错。`warmup_bars` 是固定非负整数，应覆盖参数最大窗口；例子 `ma_cross` 为最大慢线周期 200 加前一根比较留出 201 根。

`on_bar(context)` 是同步函数，只在主区间收盘后调用；预热 K 线在第一次调用时已包含在窗口中，不调用策略交易。返回 `Intent` 或 `None`：

| 成员 | 含义 |
| --- | --- |
| `history` | 截至当前收盘的只读序列，支持长度、索引、切片和迭代，不含未来；每个 Bar 含 timestamp/open/high/low/close/volume |
| `position` | 空仓为 None；否则为只读映射，包含 side、quantity、principal、entry_price、entry_time、stop、target、trailing_pct、best、trade_id |
| `cash` | 当前可用模拟现金，不含持仓本金或空头卖出所得 |
| `equity` | 可用现金＋占用本金＋未实现盈亏 |
| `parameters` | 已验证、补全默认值的只读参数映射 |

`Bar.timestamp` 是 K 线开盘 UTC Unix 毫秒；调用时该 K 线已收盘。窗口自身不复制整段历史；切片仅复制所选片段。编写长区间策略时读取必要窗口或维护增量指标，避免每根都重算全部历史。

`Intent.action` 为 `long`、`short`、`close`、`hold`；`None` 等价持有。开仓可附带 `stop_loss_pct`、`take_profit_pct`、`trailing_stop_pct`，数值使用百分数单位（5 表示 5%），均须在 0 和 100 之间，不启用时传 None。示例参数 trailing=0 会先转换为 None。`reason` 是说明文字。系统记录所有非持有信号，包括忽略和区间结束未执行信号。

利润回吐保护使用 `Intent("long", profit_protection=ProfitProtection(activation_pct=2, giveback_pct=40))`，从 `app.domain.local_backtest` 导入 `ProfitProtection`。上述设置表示最高浮盈达到入场本金的 2% 后启动，保留最高浮盈的 60%，并非价格回落 40%。两个参数都必须大于 0、小于 100。空头按入场价减去最低价计算浮盈。原反向信号仍可独立退出，不需要先达到盈利启动值；固定止损等已有保护同时存在时取更紧的有效线。

支持标准库、当前环境 NumPy、Pandas、TA-Lib 和上述公开接口。策略必须自包含，不导入项目私有模块或其他本地辅助文件，也不依赖实时网络、随机结果、当前时间或未快照化外部数据。环境是本地 Python，不是安全沙箱；这些是可重复研究的接口约定。不要自行修改账户、运行数据库或结果文件。不提供 Pine 自动转换。

## 成交、资金和统计口径

每根先检查旧仓开盘跳空止损/止盈，以开盘价退出；再执行上一收盘信号；再检查本根高低范围的止损/止盈（新仓也参与）。同时触及两者时止损优先且 `ambiguous=true`。触及边界即成交。反向信号先平旧仓再按平仓后权益开新仓；同向持仓不重复加仓，空仓平仓会记录忽略。

收盘先记录浮盈亏、权益与回撤，再调用策略。移动止损从入场即生效，距离始终为「实际入场价 × 移动止损比例」：多仓用持仓期间最高价减去该距离，空仓用最低价加上该距离。之后按已知高低价向保护利润的方向移动，新价格从下一根才有效；固定与移动止损取更有保护作用者。例如 100 入场、移动止损 10%、最高价涨到 120，下一根有效止损为 110。最后收盘强制平掉剩余持仓，原因 `end_of_backtest`；该收盘信号标为 `unexecuted_end`。保护价轨迹包含开盘跳空退出当根的有效价格；同根反向开仓分别保留旧仓、新仓的轨迹。

仓位比例范围为大于 0 且不超过 100%，数量等于权益乘仓位比例再除成交价；开仓扣本金、平仓返本金并结算价差。多仓盈亏为数量乘退出价减入场价，空仓相反。权益可为零或负数，不实施强平，权益不足时不再开仓。

交易时间保存所属 K 线的开盘时间以及 `open/intrabar/close` 阶段，不虚构盘中秒级时间。信号同时保存所属 K 线时间和真实收盘决策时间 `decision_time`。权益序列包含初始点及每根收盘点。盘中退出的持仓时长用所属 K 线开盘近似，收盘退出计至该根收盘。

报告使用完整序列计算：总收益基于初始资金；胜率为盈利交易除全部平仓交易，保本单列；平均单笔收益为各笔本金收益率算术平均；盈亏比为盈利笔平均金额除亏损笔平均绝对金额；利润因子为盈利金额合计除亏损金额绝对合计。无交易的均值/胜率、缺少盈利或亏损的盈亏比、无亏损的利润因子为空，页面显示横线。最大回撤标为「收盘权益最大回撤」，可能超过 100%；不提供盘中回撤、年化、夏普或 Sortino。

## 数据、任务和复现

周期为现有数据源支持范围与 1m/5m/15m/30m/1h/4h/1d 的交集。现有历史服务负责缓存和缺口补齐，主区间与预热都必须完整，时间戳、对齐、OHLC、成交量和有限数值检查通过才开始计算。缺失时返回具体范围，不插值或悄悄缩短。

状态为 queued → preparing → running → completed，任一步可失败或取消。现有后台同一时刻串行运行一个独立 Python 子进程，不阻塞 API 的事件循环。后台停止或重启将遗留活动任务标为 interrupted，不自动重跑；队列中的任务保留。Windows 使用 Job Object 管理计算进程及其派生进程，后台即使被强制结束，系统也会终止这组进程。计算进程收到后台启动许可后才进入任务，避免后台在进程归属设置前退出造成遗留计算。取消会终止当前计算子进程，已取消任务不能被晚到结果改成完成。归档只隐藏列表，不删除数据。

数据库使用 `local_backtest_runs` 和 `local_backtest_records`，后者按记录种类保存信号、成交、交易、权益、K 线和保护价轨迹。独立于组合账户流水。材料保存在 `RUNTIME_ROOT_DIR/local_backtests/<id>/`：`strategy.py`、`config.json`、`metadata.json`、`data.json`、`result.json` 和 `run.log`。失败任务可能尚未形成全部文件。

按快照重跑使用保存的源码、参数和行情，不调用下载。校验源码、数据哈希，以及引擎规则版本、Python 和关键依赖版本；不匹配时拒绝一致性重跑。当前 `ENGINE_VERSION=6`，在版本 5 上增加只读的 `context.last_exit`，提供最近一次真实平仓的 trade_id、side、entry_time、exit_time、exit_reason、return_pct。该信息在当根成交处理后、收盘决策前可见，包括开仓当根止损；策略须按 trade_id 去重，不能把持续存在的同一记录当作新平仓。成交、止损及利润保护顺序未改。

支持盈利保护以及按信号收盘时确定的绝对距离设置初始止损（例如 ATR）。旧版本结果仍可查看、导出，使用当前引擎需重新创建任务；没有启用新功能的基准曾验证逐笔交易和资金曲线与版本 2 完全相同，但不绕过快照的版本检查。引擎成交规则或公共策略接口变化必须更新 `ENGINE_VERSION`。同环境复现约定适用于确定性策略，不支持中间 K 线断点续算。图表始终读取该次快照的数据库记录，不用最新行情替换。

利润保护每根收盘后根据持仓期间已知的高低价更新，新的保护线从下一根生效。做多线只上移，做空线只下移。不得用当根最高价抬高保护线后，又回头使用该根更早的最低价成交。已生效的保护线可以在后续 K 线盘中触发；跳空越过时用真实开盘价，原因记为 `profit_protection`。开盘先检查旧保护线，再执行上一收盘信号；同时满足时旧仓只平一次，符合条件的反向新仓仍可开仓。旧仓平掉后新仓重新计算浮盈，不继承旧仓最高点。这个规则是十五分钟更新的模拟，不代表逐笔行情实时移动；刚创高后同根回落可能等到下一开盘才退出。

## HTTP 接口

### 有历史空档的长期研究

默认 `data_gap_policy=reject` 继续要求完整行情。核查源数据后确需使用实际存在的 K 线时，可在创建命令显式传入 `data_gap_policy: "observed_bars"`，CLI 对应 `--data-gap-policy observed_bars`。这个选项只允许区间内部缺少 K 线，不允许首尾缺失、预热不足、重复或倒序时间戳、周期错位、非法价格和未来数据。不会生成插值或零成交量 K 线。

该方式保留现有成交引擎：跨空档的持仓和待执行信号延续到下一条实际行情；跳过止损价时按该条开盘价处理。空档内部的价格路径未知，无法确认期间有没有触发退出。运行元数据保存 `history_gaps` 和处理规则，页面显示空档提示，快照重跑沿用相同策略。默认严格模式不受影响。

六年联合参数研究见 [ETH 六年联合参数测试](verification/eth-cloud-joint-six-year-20260911/REPORT.md)。固定 128 种组合、每组 9 个期间，通过 `python -m scripts.cloud_joint_study run --workers 2` 使用项目已保存行情与同一成交引擎计算，并可从已完成记录继续；`publish` 创建或核对计划内的重点版本正式图表。每组配置、源码副本、行情校验值、逐笔交易和资金轨迹均保留。排名只在相同日期范围内比较，不将两年累计收益与一年累计收益直接比较。

根路径 `/api/v1/local-backtests`，实际模型与可调用接口见应用 `/docs`，前端契约由 `npm run sync:contracts` 生成。

| 方法、路径（相对于根路径） | 用途 |
| --- | --- |
| GET `/strategies` | 策略参数、交易对、周期目录 |
| POST 根路径 | 创建运行，正文对应 LocalBacktestCommand |
| GET 根路径 | 列表，offset/limit/archived |
| GET `/{id}` | 状态、配置、来源、统计 |
| GET `/{id}/records/{kind}` | 分页，kind 为 signals/trades/fills/equity/candles/levels |
| POST `/{id}/cancel`、`/{id}/rerun`、`/{id}/archive` | 正文 `{}`，返回运行 |
| GET `/{id}/export` | format=json/trades/equity，返回文件名、类型和内容 |
| GET `/{id}/log` | 最近运行日志 |

记录接口支持 offset/limit 和 UTC 毫秒 start/end（图表查询边界均包含）；equity 可用 sampled=true 按 limit 抽样并保留每个区段的权益与回撤极值。回测输入时间区间仍是开始包含、结束不包含，二者不要混用。

## Windows 验证

### 指标图与参考信号核验

策略可以继续返回 `Intent` / `None`，也可以返回公开的 `BarResult(intent=..., values={...}, checks={...}, cloud=TrendCloud(upper, lower, bullish))`。`values` 为有限数值或 None，`checks` 为布尔条件；没有交易时仍然保存该根收盘的指标。仅传入 `cloud` 或 `values` 不产生订单。记录随结果和快照保存，HTTP 的 records kind 新增 `indicators`，无需额外数据库迁移。前端可显示云带、全部信号或实际成交，并点击 K 线检查当根条件。默认图表从主区间开始，预热数据仍在快照与记录中保留。

CLI 新增 `backtest records RUN_ID --kind indicators --limit 500` 和 `backtest compare RUN_ID --reference FILE.json --tolerance-bars 0`。参考格式为 `{"context": "参考来源", "signals": [{"timestamp": "2026-08-22T13:00:00+08:00", "action": "short"}]}`，时间使用信号所在 K 线的开盘时间，支持带时区 ISO 或 UTC 毫秒；必须对齐周期、位于运行区间内，且无重复。比较输出匹配、漏点、多余信号与参考点当根指标，比较对象是完整信号记录（含同向持仓时忽略的信号），不拿成交点冒充信号点。默认不允许前后移位；容差仅改变比较，不改变策略或快照。提供清单须覆盖本次完整区间；缺少参考信号会如实计作多余点。

需要图像数值核验时，参考 JSON 还可包含 `price_to_pixel_log: [a,b]` 和 `cloud_samples: [{timestamp,upper_y,lower_y}]`，坐标定义为 `y=a*ln(price)+b`（a<0）。采样可位于两根之间，按屏幕坐标线性插值，跨缺口和范围外不补造数据，输出像素误差及未能比较的数量。截图读取误差、图表交易所和价格类型必须单独保留。示例、两组参数和本次结果见 [ETH 云带核验](verification/eth-cloud-202608/REPORT.md)。

长期效果比较见 [ETH 15 分钟两年对照](verification/eth-cloud-two-year-20260910/REPORT.md)。`trend_cloud_comparison` 提供固定的 14 组公式／基准，`python -m scripts.trend_cloud_study status` 查询这些正常项目运行，`analyze` 从已保存行情使用同一模拟器复查历史分段。按用户要求全部不计手续费和滑点；长期排名不等同于确认截图原公式。

ATR 对照与亏损诊断见 [逐笔原因及改法比较](verification/eth-cloud-two-year-20260910/DIAGNOSTICS.md)。`trend_cloud_experiments` 提供中心线、宽度、入场过滤、连续收盘确认和 ATR 比例止盈止损参数；`python -m scripts.trend_cloud_diagnostics experiments` 按已保存的 26 组计划使用同一快照与模拟器重跑，`baseline` 生成原版本的逐笔过程诊断，`publish` 创建或核对项目可见的“不追过远价格”实验运行。该改法属于已看过历史后的探索结果，没有通过预设的首年优胜筛选。诊断器排除退出开盘所在 K 线之后的波动，遇到无法从 OHLC 判断先后顺序的盘中退出会明确拒绝推算精确浮盈亏。

利润保护和通道参数的后续试验使用 `trend_cloud_profit_protection`，计划保存在 `docs/verification/eth-profit-protection-20260910/plan.json`。`python -m scripts.profit_protection_study run` 从项目已有快照运行 9 组宽度、6 组原通道利润保护，再把同样 6 组保护用于首年选出的通道；后续区间不重新选参数。`publish` 创建或核对正常项目回测记录。报告同时保留完整交易路径、退出原因、相同入场对照，以及固定基准入场时刻以排除额外入场影响的实验。

`test/test_local_backtest_engine.py` 覆盖手算核账、双向成交、止盈止损、跳空、移动止损、未来数据隔离、最终平仓与零负权益；`test/test_local_backtest_service.py` 覆盖快照复现、数据失败、API/CLI 同输入、导出核对，以及真实 Python 子进程串行、取消和关闭中断。迁移、已有研究/组合回归、前端契约和构建也应同时通过。

真实样例：Binance BTC/USDT 现货 1h，2025-01-01 至 2025-04-01，默认 ma_cross 参数，初始 10,000、仓位 100%。下载 2,361 根（含 201 根预热），96 笔交易，期末权益 10,649.415803470534，收盘权益最大回撤 22.866525%。此数值仅作为当前快照的核对基准，不作为策略有效性的保证。

2026-09-09 已补齐原 PostgreSQL `heimdall` 环境验收，使用项目 Python 3.12.10，数据库从 `008_drop_funding_rates` 迁移至 `018_local_backtests`，结构检查通过。迁移前完整 SQL 备份为 `.heimdall_runtime/postgres-before-local-backtests-20260909.sql`；既有 009 迁移去除了 4,706 条重复指标记录，备份保留迁移前全部数据。

页面提交、CLI 提交、页面快照重跑的全部信号、成交、逐笔交易、权益、保护价和统计已在 PostgreSQL 逐项比对一致，JSON/CSV 与数据库核对一致；页面刷新、点击交易定位，以及取消、失败、非零 CLI 退出码和归档查询均通过。成功 CLI JSON 在标准输出，失败 JSON 在标准错误。首笔空仓在 2025-01-01 07:00 以 93,757.57 入场，20:00 反向信号以 94,627.08 平仓，数量约 0.106658，亏损 92.740245；页面点击该笔可见对应价格和标记。

完整后端回归 210 项通过，前端契约生成、类型检查及生产构建通过。新增测试覆盖多空移动止损入场基准、止损单向移动、跳空退出保护价、同根反向仓位轨迹、旧引擎版本拒绝重跑，以及真实 Windows 后台被强制结束后计算进程和派生进程退出、重启后原任务中断且队列继续执行。原数据库验收记录保存在 `.heimdall_runtime/postgres-local-backtest-verification-20260909.json`。
