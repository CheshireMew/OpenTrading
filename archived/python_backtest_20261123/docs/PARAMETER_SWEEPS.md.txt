# 批量参数比较

比较轴支持 `parameters.*`、`timeframe`、`position_pct`、`execution_timeframe` 和 `intrabar_profit_protection`。成交周期列表的 `null` 表示不使用细周期（页面填 `none`）；不能与启用细周期保护组合，冲突会在预览时明确报错。界面、保存的组合配置和 CSV 均保留仓位与执行设置。

“检查组合”会显示各组规则、预热、主周期与细周期的本地覆盖，以及全部组合的共同覆盖区间。这里只检查缓存，不下载行情、修改日期或加入队列。同源同周期组合使用本批所需的最大预热长度，使参数配对使用相同历史；旧结果复用还必须满足这一冻结设置。改变信号周期的对照单独标明聚合差异，改变成交周期的对照单独标明细行情差异，不冒充相同行情的单参数效果。

输入多个参数后，由软件自动组合、回测、排序并保留完整本地记录。用户用界面，外部 Agent 用同一个服务的 CLI/API，无需再为每次参数对比编写运行脚本。

## 界面

进入“研究 → 批量参数比较”；也可在任意已完成的单次回测中点击“用这组参数批量比较”，继承全部设置，包括细周期成交数据和利润保护更新频率。

1. 选择策略、标的、交易周期和 UTC 历史区间。
2. 勾选要比较的参数，填 `34, 55, 89` 等明确取值，或填写起点、终点、步长。不勾选的参数保持固定。也可比较不同交易周期。
3. 页面显示组合数；“检查组合”只校验输入，不下载行情。“开始批量回测”保存并自动入队。
4. 完成后默认按收益率排序，同时展示胜率、赚钱/亏钱次数、总笔数和回撤。点击“查看 K 线”进入逐笔复盘。CSV 包含所有组合，包括失败和零交易项。
5. “查看参数影响”只比较其他输入、源码和行情相同的结果。它统计改变这个参数后多少组收益提高，收益差中位数是多少；没有合格配对则不下结论。

关闭页面继续运行，需保持项目后台启动。取消保留已完成结果，恢复只补交/重试未完成项。复制参数另建一版保留旧版，重试也另留运行记录。

范围包含起点，按步长递增，不超过终点，例如 `1 → 2，步长0.7` 得到 `1, 1.7`。十进制展开避免浮点尾差；重复值去重。每批最多512组，不自行扩大范围。

## 外部 Agent 入口

输入文件示例（未填写的策略参数使用默认值，实际完整值会被冻结）：

```json
{
  "title": "ETH：比较 EMA 和突破门槛",
  "base": {
    "strategy": "trend_cloud_intrabar_methods_v3",
    "symbol": "ETH/USDT", "timeframe": "15m",
    "start": "2024-09-10T00:00:00Z", "end": "2026-09-10T00:00:00Z",
    "initial_cash": 10000, "position_pct": 100,
    "execution_timeframe": "5m", "intrabar_profit_protection": true,
    "data_gap_policy": "observed_bars",
    "parameters": {
      "center_length": 55, "width_length": 31, "trigger_mult": 0.4,
      "chase_mult": 2, "confirmation_level": 3, "max_wait_bars": 2,
      "initial_stop_pct": 1, "stop_method": 0,
      "activation_pct": 2, "giveback_pct": 50
    }
  },
  "axes": {
    "parameters.center_length": [34, 55, 89],
    "parameters.trigger_mult": {"start": 0.4, "end": 0.8, "step": 0.4}
  }
}
```

在项目根目录运行：

```powershell
.\venv\Scripts\python.exe -m scripts.research_cli sweep preview --file D:\path\request.json
.\venv\Scripts\python.exe -m scripts.research_cli sweep create --file D:\path\request.json
.\venv\Scripts\python.exe -m scripts.research_cli sweep status BATCH_ID --limit 5
.\venv\Scripts\python.exe -m scripts.research_cli sweep effects BATCH_ID
.\venv\Scripts\python.exe -m scripts.research_cli sweep cancel BATCH_ID
.\venv\Scripts\python.exe -m scripts.research_cli sweep resume BATCH_ID
.\venv\Scripts\python.exe -m scripts.research_cli sweep export BATCH_ID --output D:\path\results.csv
```

`list` 查历史；`status --offset 5 --limit 5` 分页；支持 `--sort win_rate`、`--sort max_drawdown_pct --ascending`、`--minimum-trades 20`。状态默认只返回10项，不读取逐笔大文件。导出文件必须尚不存在。

可选 `source_run` 指定已完成回测。输入区间、标的、周期、预热相同时复用该次冻结行情；配置、源码和引擎相同的组合直接复用结果。代码变了就重新计算。可选 `parent` 关联上一批次。

API 前缀 `/api/v1`：`POST /parameter-sweeps/preview`、`POST /parameter-sweeps`、`GET /parameter-sweeps`、`GET /parameter-sweeps/{id}`、`POST /parameter-sweeps/{id}/action`（`{"action":"resume"}`或`cancel`）、`GET /parameter-sweeps/{id}/effects`、`GET /parameter-sweeps/{id}/export`。API 只提交，后台计算。

## 速度、记录与边界

后台默认同时运行2组独立进程。相同标的、区间、交易周期、成交周期、预热和空档约定的组合共享一份经过检查的行情，再分别保存完整结果。文件锁和哈希检查避免共享半成品数据。取消一组不影响另一进程。

多年行情按每段最多10,000根分段准备，每段完成后保存并校验。接口超时或任务中断后，恢复会复用已完成的分段；不足区间边界的数据不会冒充完整结果。页面在下载阶段也显示进度。

运行目录 `research_studies/<批次ID>/` 保存不可变的输入 `sweep.json`、全部组合与版本 `plan.json`、源码及引擎快照 `sources/`、追加事件 `events/`、完成后的排名 `rankings/`。各运行在 `local_backtests/<运行ID>/` 保存参数、行情、引擎、源码、逐笔结果和日志。共享行情在 `parameter_sweep_data/`。改参数始终新建批次。

这里比较指定历史，不自动证明未来最优。要提前锁定参数、留出后续历史时，继续使用已有 `study` 选择/验证流程。不要为了增加组合而超出用户要求。
