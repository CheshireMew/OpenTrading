# v7.2 来源与事件核对

交付源码仍为 `strategies/pine/eth_ema55_manual_chart_v7_2.pine`，本轮没有改写 Pine。相邻的 `.manifest.json` 保存规则版本、Pine 和原报告校验值、当前图表周期约定、主动差异与标签定义。它不把历史 5 分钟保护版本的收益归给当前图表周期版本。

运行 `python -m scripts.verify_pine_contract` 可核对当前源码身份、禁止小周期请求、标签文字颜色、止损检查先于收盘更新保护的结构，以及五个共享 OHLC 事件样例。`--output PATH` 可保存 JSON 检查结果。样例隔离等待到期、只平仓不反手、保护下一根生效、模糊入场根止损和开盘超过追价上限；其中指令明确给定，不构成完整 EMA 信号验证。

检查报告将 Python 执行结果、Pine 规则片段检查、TradingView 编译和 Pine 实际事件对照分开。本地检查器不操作 TradingView，因此其本次执行字段仍为 `not_verified`；已经完成的浏览器验证另存于 manifest 和下述记录，不能把本地命令重跑当成重新编译 Pine。

项目复盘图使用同一套中文标签与颜色。只有已记录的反向退出后确实开仓才合并成“平仓做多／平仓做空”；止损后新开仓保留为两个事件，同根入场和止损也不会被隐藏。原始退出原因仍在交易详情和过程里明确显示。

2026-09-20 应用户要求完成 TradingView 实际验证。最初内置浏览器要求登录，随后 Edge 曾断开；重新打开用户指定的 Edge 后，在已经登录的 ETHUSDT 15m 图表中成功编译并添加原版 v7.2。编辑器完整内容与本地源文件在统一换行后逐字符一致，原 Pine 源码未改动。

随后执行独立验证脚本：650 根固定预热，接入 240 根固定合成 OHLC；Python 使用 v3、实体确认、等待两根及与 Pine 相同的默认参数。验证脚本由原 Pine 自动生成，仅替换输入行情，并在真实成交分支插入观察记录，保留完整 EMA 信号和交易控制流程。TradingView 图表和 Pine logs 均显示 `PASS | bars=240 | events=38/38 | mismatches=0`，逐笔日志与 Python 预期完全一致，价格容差为 1e-7。19 笔交易含 12 次利润保护退出、6 次固定止损和 1 次反向信号退出；同根开仓止损与反向退出后开仓也在样例中出现。没有把这组合成样例的结果推广为完整历史或实时逐 tick 一致。

固定输入、Python 参数和预期值保存在 `runtime-fixture-20260920.json`；实际执行的脚本为 `runtime-harness-20260920.pine`；原版编译、恢复过程和 Pine 实际日志保存在 `tradingview-attempt-20260920.json`。可依次运行 `python -m scripts.build_pine_runtime_fixture`、`node scripts/pine_runtime_harness.cjs` 重新生成输入与脚本，再在 TradingView 手工运行后核对日志。生成命令本身不代表 Pine 已执行。临时脚本及本次添加的重复指标已通过撤销恢复，没有发布脚本。
