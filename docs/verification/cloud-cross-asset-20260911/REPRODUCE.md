# 本轮复测与恢复

本轮只新增研究文件，未修改原策略和模拟器。固定名单是 48 个策略版本和 2 项参照，包含最早全部 12 个策略版本。原始 9 批、280 条记录的索引见 history-inventory.json；参数变体和重复基准不能算成 280 种独立交易思想。

配置冻结在读取 BTC 结果之前。ETH：2020-09-10 至 2026-09-10；BTC：2018-09-10 至 2026-09-10，另列相同六年。均为 UTC、15 分钟，结束时间不包含在内。逐年区间为每年9月10日至次年9月10日。

使用项目 MarketDataService、KlineStore 和 app.domain.local_backtest.simulate。资金为每次当时的全部权益，无杠杆、无手续费、无滑点。部分源策略的入场、退出条件不同，完整参数和来源以 plan.json、源码副本为准，不重新拼装旧版本。

在 D:/Code/Heimdall 中，使用 D:/Code/Heimdall/venv/Scripts/python.exe 执行：

```powershell
# prepare 已运行；存在冻结计划时它会拒绝覆盖。
# fetch 可恢复已保存的分段行情；现有完整快照会校验哈希后复用。
& 'D:/Code/Heimdall/venv/Scripts/python.exe' -m scripts.cloud_cross_asset_study fetch
& 'D:/Code/Heimdall/venv/Scripts/python.exe' -m scripts.cloud_cross_asset_study study --workers 6
& 'D:/Code/Heimdall/venv/Scripts/python.exe' -m scripts.publish_cloud_cross_asset_study
& 'D:/Code/Heimdall/venv/Scripts/python.exe' -m scripts.audit_cloud_cross_asset_study
& 'D:/Code/Heimdall/venv/Scripts/python.exe' -m scripts.render_cloud_cross_asset_study
```

study 会校验输入、复用已经完成的相同记录，不会根据新结果调整参数。若要改变规则或参数，应新建另一轮目录，不覆盖本轮。

研究目录：D:/Code/Heimdall/docs/verification/cloud-cross-asset-20260911。

运行材料：D:/Code/Heimdall/.heimdall_runtime/cloud-cross-asset-20260911，其中 configs 保存逐版本参数，sources 保存源码副本，traces 保存 ETH/BTC 各期间的逐笔交易、信号、权益和统计。ETH 原行情快照复用前一轮文件，具体路径和哈希在 data.json 中。

历史副本保存在 docs/verification/eth-cloud-robustness-20260910/versions。029 保存本轮冻结名单和策略，030 保存报告/核验工具及行情收据；完成时再追加完整记录副本。已有副本不删除、不改写。

报告地址：http://127.0.0.1:8787/cross-asset.html。此页由同名 report.html 生成。项目图表使用正常的回测记录，可通过 report.html 的链接打开。

历史数据有内部空档，已通过项目数据接口补查；没有生成替代K线。跨空档时沿用项目既有的观测K线处理方式，无法知道空档内的真实路径。年度从空仓开始，完整多年回测连续持仓，因此不应直接把独立分年收益连乘当作多年结果。
