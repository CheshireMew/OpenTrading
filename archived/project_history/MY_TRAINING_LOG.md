# 我的 7 天量化实战记录

## Day 1

### 今天只研究一个问题

从回测页面点下“开始回测”后，请求到底怎么走到后端，并真正产出一条可查看的回测记录。

### 今天确认的最短链路

前端入口在 `frontend/src/modules/backtest/api.ts` 的 `backtestApi.startRun()`，它向 `POST /api/v1/backtest/start` 发请求。

后端收到请求后，`app/routers/backtest.py` 会把页面提交的数据整理成 `BacktestStartCommand`。

接着 `app/services/backtest/command_service.py` 做两件事：

1. 取出策略版本
2. 按 `days` 反推出本次回测的起止时间

最后 `app/services/backtest/run_service.py` 调用 Freqtrade 执行回测，并把结果写入数据库表 `backtest_runs`、`backtest_trades`、`backtest_signals`、`backtest_equity_points`。

### 我今天实际跑过的基线

先用默认策略 `ema_rsi_macd` 跑过 30 天和 90 天，链路是通的，但这两次都没有触发成交。说明系统没有坏，只是这组条件在这段行情里没有发出买卖信号。

为了留下第一条“有真实成交”的基线记录，我继续用同一条 API 链路测试了内置策略，最终选用下面这条作为 Day 1 基线：

- 回测 ID：`40`
- 策略名：`bbands_mean_reversion`
- 交易对：`BTC/USDT`
- 时间周期：`1h`
- 回测天数：`90`
- 起止时间：`2025-12-27 22:40:00` 到 `2026-03-27 22:40:00`
- 收益率：`-0.3217%`
- 最大回撤：`1.8132%`
- 交易次数：`5`
- 买入信号：`5`
- 卖出信号：`5`
- K 线数量：`2160`

### 这次基线使用的关键参数

今天的目标是先跑通，不做优化，所以我把研究分支先关掉了，避免第一次回测被训练集拆分和参数搜索干扰：

- `in_sample_ratio=100`
- `optimize_trials=0`
- `rolling_windows=0`

这样本次结果就是一次完整的全样本直接回测，更适合作为第 1 天的基线。

### 改动前后结果

今天没有改代码，只有实战验证和记录，所以这里的“改动前后”对应的是策略切换后的结果对比：

- `ema_rsi_macd`，`90` 天，`BTC/USDT`，成交 `0`
- `bbands_mean_reversion`，`90` 天，`BTC/USDT`，成交 `5`
- `breakout_volume`，`90` 天，`BTC/USDT`，成交 `1`

### 今天的结论

今天真正确认的事实不是“哪个策略赚钱”，而是：

1. 回测全链路已经跑通
2. 默认趋势策略在最近 90 天 BTC 1 小时级别上没有触发成交
3. 同样的数据和接口下，均值回归模板已经能产出可比较的真实基线

所以 Day 2 更适合基于 `bbands_mean_reversion` 做参数实验，而不是继续拿 `ema_rsi_macd` 空跑。

### 统一验证

- `pytest -q`
- `python -m compileall app`
- `cd frontend && npm run build`

### 验证是否通过

已通过。

- `pytest -q`：`12 passed`
- `python -m compileall app`：通过
- `cd frontend && npm run build`：通过
