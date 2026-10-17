# 短观察窗口与调整频率测试

用户批准的范围：ETH、BTC、PAXG、ZEC；5分钟、15分钟、半小时、1小时 × EMA34/55/89 × 突破0.4/0.8倍，共24套。固定高低差EMA31、不追超过2倍、初始止损1%、浮盈2%启动保护、回吐50%、反向一根确认。ATR不参与本轮选择。

比较看过去2/4/8/12周，每1/2/4周重新选择的12种办法。按当时以前窗口的账户收益排名；要求正收益及至少20笔窗口内开仓且已完整平仓的交易。20笔是预先固定的筛选条件，不是显著性证明。无合格候选则空仓。参数没变继续原仓；改变时在调整日实际开盘价平掉旧仓，取消旧挂起信号，新参数等待自己的新信号。没有每周统一强制清仓。

共同来源历史2020-10-01起，最长12周观察后，从2020-12-28到2026-09-10检验；因此是接近六年的来源历史、五年八个多月的可交易检验，不能写成完整六年收益。每周边界采用UTC周一00:00。所有版本同起止日期，100%本金复投，无手续费、滑点或杠杆。

另用2024-09-09以前的累计表现，从12种窗口/调整办法中先固定一种，单列它在之后两年的表现。每次选择策略参数仍只看最近2—12周；较早几年只用于评价哪一种窗口办法更值得保留。全期第一名只能称为事后比较第一，不能冒充事先选定的版本。所有历史已被研究过，本轮不是未接触过的最终留出集。

## 运行

```powershell
venv/Scripts/python.exe -m pytest test/test_cloud_short_window.py -q
venv/Scripts/python.exe -m scripts.cloud_short_window_study prepare
venv/Scripts/python.exe -m scripts.cloud_short_window_study lock
venv/Scripts/python.exe -m scripts.cloud_short_window_study run --workers 4
venv/Scripts/python.exe -m scripts.cloud_short_window_study lock-method
venv/Scripts/python.exe -m scripts.cloud_short_window_study finish
venv/Scripts/python.exe -m scripts.report_cloud_short_window
```

准备步骤冻结参数、代码和测试哈希。lock复用上一轮96份候选路径与16份项目原生行情，重新计算每次当时以前的分数，保存选择，不读取后续政策收益。run仅向总进程返回早期评价值，后段轨迹保存在本地。lock-method只接收早期数值，随后finish才汇总完整表现。

旧策略和引擎保持不变，新增独立的参数切换研究引擎。无需切换时，该副本与原引擎一致；原策略经过完整历史预热与连续指标状态恢复输出相同。数据和大体积逐笔记录在D盘`.heimdall_runtime/cloud-short-window-20260912`，方案、选择、得分、最终汇总在本目录，所有版本进入已有编号归档。

中断可按上述顺序恢复。已完成文件复用，不覆盖不同内容或删除历史。若进程异常退出留下不完整文件，先核验准确路径并归档，再继续，不删除。
