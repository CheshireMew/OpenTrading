# 四标的周期选择、利润保护、ATR与反向确认研究

本轮只用原EMA通道策略，标的是PAXG、ZEC、ETH、BTC。参数与选择办法在计算前冻结于plan.json；旧源码、旧策略与旧结果均保留。

## 固定范围

- 周期：5分钟、15分钟、30分钟、1小时、日线。
- 入场候选：EMA34/55/89 × 突破0.4/0.8倍 × 初始百分比止损1%/2%，共12套。
- 固定项：高低差EMA31，不追超过2倍宽度，浮盈2%启动保护。
- 利润保护：回吐50%、35%、25%；回吐50%另加价格回撤5%或10%上限。
- 配对风险对照：原百分比止损、ATR14的2倍、ATR14的3倍，每种分别使用反向1根/2根收盘确认。与五种保护方式交叉。
- 每笔当前全部本金复投，不计手续费和滑点，不加杠杆。

日内周期用2020-10开始的历史，每次此前三年选择，2023-10开始检验后面半年，共六段，最后一段结束于2026-09-10。日线共同历史需等到2022-10，含日线的三年选择只能用于2025-10以后的两个后续段；两种期间分开报告。

选择优先附近参数与六个历史半年通常表现都为正的设置；自身三年盈利、至少30笔已平仓交易，否则空仓。选择函数不接收后续收益。另保留只挑过去收益最高的选择对照。计算机可预先缓存因果行情路径，但模型不查看后续排名，不依其修改选择办法。

风险和保护的配对比较有两种入场依据：一是原50%方法按过去选出的入场设置，二是固定原ETH参数的1小时设置。后者在自动选择空仓时仍能提供真实交易对照。这些配对结果不用于倒选后续赢家。

## 运行与恢复

在项目根目录，使用项目venv下的Python，依次运行：

```powershell
venv/Scripts/python.exe -m scripts.cloud_walkforward_study prepare
venv/Scripts/python.exe -m scripts.cloud_walkforward_study fetch --workers 4
venv/Scripts/python.exe -m scripts.cloud_walkforward_study train --workers 4
venv/Scripts/python.exe -m scripts.cloud_walkforward_study lock
venv/Scripts/python.exe -m scripts.cloud_walkforward_study replay --workers 4
venv/Scripts/python.exe -m scripts.cloud_walkforward_study audit
venv/Scripts/python.exe -m scripts.analyze_cloud_walkforward_exits
venv/Scripts/python.exe -m scripts.report_cloud_walkforward
```

已完成的行情块、候选和后续重放均按文件恢复，不删除既有记录。源文件哈希不一致会停止。改变设计须保留旧版并建立新版本，不能在看到结果后改写本轮规则。

## 记录位置

- `plan.json`：冻结范围和选择办法。
- `data.json`：项目行情文件与哈希；原始行情路径仍保留。
- `native-data-check.json`、`native-live-recheck.json`、`data-before-live-correction.json`：ETH/BTC四根旧缓存的发现、交易所复查与修正前清单。
- `engine-baseline-verification.json`：关闭新增价格回撤上限时，原ZEC小时两年1,154笔逐笔、信号、权益与报告完全一致。
- `training.json`：用于选择的历史窗口得分。
- `selection-lock.json`：在实际后续分段重放之前锁定的选择。
- `replays.json`：后续每段模拟索引。
- `results.json`、`verification.json`：最终统计与核对记录。
- `.heimdall_runtime/cloud-walkforward-20260911`：所有逐笔与信号、候选按日/边界权益、实际后续逐根权益，使用gzip保存。
- `docs/verification/eth-cloud-robustness-20260910/versions`：按编号保留过程副本。

半年边界由事先固定的日期决定，统一清仓，下段重新从空仓开始，收益带入下段；不会根据行情临时换策略。所有报告须说明这段历史已经研究过，不能声称是真正未接触过的数据或已排除过拟合。
