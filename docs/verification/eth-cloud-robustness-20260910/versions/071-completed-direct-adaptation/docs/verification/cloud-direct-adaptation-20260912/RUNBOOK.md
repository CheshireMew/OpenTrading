# 运行与恢复记录

工作目录：D:/Code/Heimdall。Python：venv/Scripts/python.exe。无需下载新行情，复用项目已校验快照。

按顺序执行：

```powershell
& 'D:\Code\Heimdall\venv\Scripts\python.exe' -m pytest test/test_cloud_direct_adaptation.py -q
& 'D:\Code\Heimdall\venv\Scripts\python.exe' -m scripts.cloud_direct_adaptation_study prepare
& 'D:\Code\Heimdall\venv\Scripts\python.exe' -m scripts.cloud_direct_adaptation_study run --workers 2
& 'D:\Code\Heimdall\venv\Scripts\python.exe' -m scripts.diagnose_cloud_direct_entries
& 'D:\Code\Heimdall\venv\Scripts\python.exe' -m scripts.report_cloud_direct_adaptation
```

本轮已完成96个回测，7个针对性测试通过。8个原版对照与原引擎所有返回字段完全一致；96份逐笔文件哈希及冻结源码均通过核验。入场过滤的8个资产/周期对照中，共同入场交易的退出时间和价格相同。

计算结果位于 `.heimdall_runtime/cloud-direct-adaptation-20260912/traces`，所有规则、统计与源码哈希位于本目录。`plan.json`及逐笔统计不可事后改写，重复执行会核对既有文件。若运行中断留下半份文件，应先保留到中断归档目录，不能删除或冒充完整结果。

后台计算日志：`.heimdall_runtime/direct-adaptation.out.log`、`.heimdall_runtime/direct-adaptation.err.log`。本轮日志最终为 `COMPLETE96 fixed-formula tests;8 original controls exact`，错误日志为空。

网页：`http://127.0.0.1:8787/cloud-direct-adaptation.html`，由现有8787服务提供。本轮只增加独立研究策略、引擎副本、脚本与报告，没有改动原模拟器、旧策略或产品交易入口。

副本：069改动前；070冻结方案；071完成后。所有新指标使用已收盘价格。自动均线是ER31线性调整EMA21—89，并非标准KAMA。
