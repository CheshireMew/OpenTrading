# 策略研究：先查旧证据，再做有边界的实验

只需批量比较参数时，用[批量参数比较](PARAMETER_SWEEPS.md)的界面或 `research_cli sweep`。不用再为简单参数测试填写研究计划或临时写执行脚本；下面的 `study` 保留用于提前锁定参数、验证顺序和正式结论。

面向 Codex、Claude Code 等外部工具。入口是 `python -m scripts.research_cli`，使用项目现有行情服务、回测队列和图表。没有内置 Agent，也没有另一套交易引擎。

## 一次研究怎样完成

1. **查旧结果。** 用 `catalog search` 找到以前测过的标的、周期、参数及结论。先回答已有证据能回答的部分。
2. **固定问题和范围。** 保存目标、判断标准、停止条件、策略家族、问题列表和案例。改变目标、资金算法、周期范围或策略结构时，另建带 `parent` 的研究，说明改动原因。
3. **预览，再建记录。** `study preview` 不下载行情、不排队。它显示案例数量、复用数量、真实日期、预热所需时间和已见历史提示。`study create` 冻结代码与完整参数，也不启动回测。
4. **按阶段运行。** `study submit` 只提交尚未提交的探索／选择案例。完成后用 `study select` 锁定版本，再次提交才运行这些版本的验证／测试案例。选择不能在看过结果后原地改写。
5. **逐项回答。** `study answer` 为计划中的每个问题保存结论、证据、适用范围、限制和去留判断。排行榜不能代替这些答案。
6. **结束或修订。** `study complete` 检查必要回测完成、问题已回答和证据文件完整。后续变更创建子研究，旧计划、回测与答案都保留。

成功输出为 `{schemaVersion:1,ok:true,command,data}`，失败退出码为 1，错误写 stderr。提交中部分案例失败时，已排队案例保留；用 `status` 查状态，再重试，不要重新创建整批研究。实际执行需要项目原有后台运行时开启。

## 查询，默认只拿需要的内容

```powershell
# 首次或旧资料发生变化时建立／增量更新索引
.\venv\Scripts\python.exe -m scripts.research_cli catalog refresh
.\venv\Scripts\python.exe -m scripts.research_cli catalog search "PAXG EMA89" --limit 4

# 查新研究的摘要、尚未回答的问题，或按范围读取结果
.\venv\Scripts\python.exe -m scripts.research_cli study list --query "通道"
.\venv\Scripts\python.exe -m scripts.research_cli study status <研究ID>
.\venv\Scripts\python.exe -m scripts.research_cli study results <研究ID> --symbol ETH/USDT --timeframe 1h --limit 10

# 原始数据留在磁盘；只读摘要或需要的逐笔分页
.\venv\Scripts\python.exe -m scripts.research_cli backtest result <回测ID>
.\venv\Scripts\python.exe -m scripts.research_cli backtest records <回测ID> --kind trades --limit 20
.\venv\Scripts\python.exe -m scripts.research_cli backtest breakdown <回测ID>
.\venv\Scripts\python.exe -m scripts.research_cli backtest compare-runs <基准ID> <对照ID>
.\venv\Scripts\python.exe -m scripts.research_cli study effect <研究ID> --factor parameters.center_length
```

`backtest result` 现在默认只返回摘要。旧调用若确实依赖全部 K 线、交易和权益数组，需要显式加 `--full`。大文件优先 `backtest export --output <路径>`，不要把完整数组送进对话。`study results` 给出现有项目图表路径，查看图表不要求再跑一次回测。

`breakdown` 直接读取保存的交易，返回多空、平仓原因、平仓年份／月份、持仓时间和大赢家集中度。月份中的 `profit` 是该月平仓交易的账户金额贡献，**不是月收益率**；它既不是每月本金重置的回测，也不是连续账户的月末盯市收益。

`compare-runs` 列出全部输入差异及数据、引擎、源码差异。`study effect` 只汇总其他输入与快照完全相同的单因素配对；没有合格配对就返回空结果，不拿排名或不同期间的收益率猜参数贡献。同时改了 EMA、时间周期和止损时，必须按组合变化解释。

## 计划格式

支持显式 `cases`，也支持较短的 `base + axes + periods`。下例仅说明文件格式，不是本次要执行的策略实验；所有时间、参数、判断标准都应按当次用户目标填写。

```json
{
  "title": "均线周期的配对检查",
  "family": "ma_cross",
  "objective": "检查改变快线周期的影响",
  "decision_rule": "比较同条件收益差，分别回答选择期和后期是否一致",
  "stop_rule": "回答本次问题后停止，不追加更细网格",
  "change_reason": "固定慢线和退出规则，只改快线",
  "max_new_runs": 4,
  "questions": [{"id": "speed", "text": "改变快线后，前后两段的结果是否一致？"}],
  "base": {
    "strategy": "ma_cross",
    "symbol": "BTC/USDT",
    "timeframe": "1h",
    "start": "2024-01-01T00:00:00Z",
    "end": "2025-01-01T00:00:00Z",
    "parameters": {"slow": 30},
    "initial_cash": 10000,
    "position_pct": 100,
    "data_gap_policy": "reject"
  },
  "axes": {"parameters.fast": [10, 12]},
  "periods": [
    {"name": "选择期", "start": "2024-01-01T00:00:00Z", "end": "2025-01-01T00:00:00Z", "role": "selection", "previously_seen": true},
    {"name": "后期历史复核", "start": "2025-01-01T00:00:00Z", "end": "2026-01-01T00:00:00Z", "role": "test", "previously_seen": true}
  ]
}
```

`axes` 可改变 `parameters.<参数名>`、`symbol`、`timeframe`。程序展开并冻结案例，创建前检查数量预算，不按收益自动挑答案。案例 ID 如 `v1-p1`；`variant` 如 `v1`。同一参数在不同周期的效果是不同实验，不能只用 EMA55 作为完整版本名称。

显式案例字段为 `id,name,variant,period,role,previously_seen,command`。复用旧结果时加 `reuse_run`，填写与旧结果完全一致的输入；允许省略旧参数的默认值，最终保存完整参数。复用会检查旧代码和行情哈希，只使用该次保存的数据，不把今天修正后的缓存当成旧数据。

```powershell
.\venv\Scripts\python.exe -m scripts.research_cli study preview --plan D:\研究\plan.json
.\venv\Scripts\python.exe -m scripts.research_cli study create --plan D:\研究\plan.json
.\venv\Scripts\python.exe -m scripts.research_cli study submit <研究ID>
.\venv\Scripts\python.exe -m scripts.research_cli study select <研究ID> --variant v1 --reason "依据已完成的选择期，按计划保留这个版本"
.\venv\Scripts\python.exe -m scripts.research_cli study submit <研究ID>
.\venv\Scripts\python.exe -m scripts.research_cli study submit <研究ID> --retry v1-p2
```

重试仅用于失败、取消或中断案例，旧运行保留。若上次已有完整行情快照，会校验后复用；未完成数据准备则仍由项目行情服务获取。重复执行普通 `submit` 不会自动重跑失败案例。状态检查直接读取持久化记录，不要求进程一直等待。

主动放弃使用 `study stop <研究ID> --reason "停止的具体原因"`。它取消本研究自己提交的未完成任务，保留旧结果、失败记录和未答问题，状态记为停止，不冒充已完成。显式复用的其他研究结果不受影响。

## 保存分析证据与答案

```powershell
.\venv\Scripts\python.exe -m scripts.research_cli study attach <研究ID> --name paired-v1 --file D:\研究\paired.json --description "相同条件配对的完整计算输出"
.\venv\Scripts\python.exe -m scripts.research_cli study answer <研究ID> --file D:\研究\answer.json
.\venv\Scripts\python.exe -m scripts.research_cli study complete <研究ID>
```

答案示例：

```json
{
  "question": "speed",
  "conclusion": "填写本次证据实际支持的结论，不只填第几名",
  "evidence": ["case:v1-p1", "artifact:paired-v1"],
  "scope": "填写标的、周期、日期和比较条件",
  "limitation": "说明同时改变的因素、已经看过的历史或样本不足",
  "decision": "inconclusive"
}
```

`decision` 可用 `keep/reject/inconclusive`。对同一问题提交修订答案会追加一条记录，不覆盖旧答案。`study history` 可读事件；`study plan` 可读全部冻结参数。证据文件按内容哈希复制保存，后续改动原文件不会改变旧研究证据。

## 本地保存的内容

- `.heimdall_runtime/research_studies/<研究ID>/`：完整计划、按哈希保存的策略源文件、逐次提交／选择／答案记录、附件原件。
- `.heimdall_runtime/local_backtests/<回测ID>/`：策略、配置、环境、行情、完整结果和运行日志；数据库保存对应分页记录。两处通过回测 ID 关联，不为同一结果额外写一套报告数据。
- `.heimdall_runtime/research_catalog.sqlite`：旧资料的派生索引，可重建，不是原始证据。索引提供文件路径、JSON 位置或行号、建立索引时的哈希。原始 K 线、逐笔和版本副本不重复索引；超大或损坏文件明确报告。

JSON 检查点使用临时文件写完后替换；研究修改由系统文件锁串行化，进程退出会释放锁。排队前先记录确定的运行 ID，中途退出后复用该 ID，避免出现两个相同任务。回测同时检查数据、源码和引擎环境；新运行也记录引擎源码与结果文件哈希。

## 软件能约束什么，不能替人决定什么

同一标的的选择、验证、测试时间不允许倒序或重叠。全期描述性比较使用 `exploration`，不冒充未见检验。`previously_seen` 是研究者申明，软件不能判断某个人是否在别处看过行情。已经反复查看的 ETH、BTC、PAXG、ZEC 历史不得仅换个标签就变成未见数据。

标准回测接口只接受已支持并可快照保存的策略。早期专用引擎、脚本和报告继续保留并可检索；不会为了放进新表格而用新引擎偷偷改算一遍。若需要迁移旧策略，必须单独做逐笔一致性检查，迁移前后保留独立版本。

新数据的真实完整性由原回测工作进程在交易计算前检查。预览只验证输入和计算所需预热时间，不声称已经完成全市场数据质量审计。`observed_bars` 必须显式声明；不可静默补造缺失 K 线。预热多少根、依据多长历史做选择都需要解释，不能所有周期机械套同一个日历长度。

软件不能保证一个历史赢家未来继续盈利，也不能仅凭亏损的退出原因证明亏损病因。先确定什么问题值得做，再使用这些工具；不要用自动批量提交扩大研究范围。手续费、滑点、仓位、排名目标听从当次用户约定，不自行添加。

本次经验与证据见 [会话复盘](STRATEGY_RESEARCH_RETROSPECTIVE_20260912.md)。
