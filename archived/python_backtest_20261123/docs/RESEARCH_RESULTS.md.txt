研究结果目录用于查找已有运行与旧研究汇总，不会启动回测。页面入口是「研究 → 研究结果目录」；结果详情可跳转到原回测的图表和诊断。

新完成的运行自动登记。查询时还会同步数据库中的历史完成记录及归档状态，因此索引中断不会改变回测成功状态。`research_results.sqlite` 只是派生目录，原始运行、汇总与明细保留在原位置。

```powershell
.\venv\Scripts\python.exe -m scripts.research_cli catalog import
.\venv\Scripts\python.exe -m scripts.research_cli catalog results --symbol ETH/USDT --family "EMA 通道" --parameter center_length=55 --parameter width_length=31 --execution-timeframe 5m --protection execution
.\venv\Scripts\python.exe -m scripts.research_cli catalog get "run:运行编号"
.\venv\Scripts\python.exe -m scripts.research_cli catalog results --reference-id "run:运行编号"
```

`catalog results` 可按策略标识、系列、标的、信号周期、完整起止区间、成交周期、保护更新方式及参数筛选。起止时间要求精确匹配，并统一到 UTC。`--execution-timeframe none` 选择已知没有细周期的运行；留空不筛选。`--parameter` 可以多次使用，等号后是 JSON 值。排序支持收益率、胜率、回撤和交易次数，`--ascending` 切换升序；`--minimum-trades`、`--offset`、`--limit` 和 `--include-archived` 控制结果范围。

历史排序回答已登记记录的数值高低，不要求所有记录具有相同实验条件。指定 `--reference-id` 后，只有区间、数据来源与校验值、策略代码、执行依赖、预热、资金、仓位和执行规则均有记录且相同的结果进入排序。参数可以不同，所以同条件排序也不自动证明单一参数的作用。旧记录缺少证据时仍能查看，不能凭两边都缺少同一字段就认定一致。

`catalog import --root 路径` 可以指定一个汇总文件或目录。默认读取 `docs/verification` 中的汇总；识别明确的 `report` 对象和计划中声明的参数/区间矩阵，跳过原始行情、逐笔数组和版本副本。引用已知 `run_id` 或 `run` 的汇总会关联本地运行；带相同明细路径与校验值的引用合并为一条结果。摘要不一致时保留独立证据。未提供的字段标为未知，不按文件名猜测。

当旧报告把结果、参数和规则分散在多个文件时，可使用 `catalog_manifest_version: 1` 的显式关联文件。项目实例是 `docs/verification/RESULT_CATALOG_SOURCES_20260915.json`。每条关联包括实际报告的路径、JSON pointer、SHA-256，声明的配置与系列，以及支撑配置的计划/规则文件及 SHA-256。映射不能直接提供收益数值，也不能补造原执行依赖。来源或上下文变化后旧关联会撤回，重新核对后再导入。BTC 示例只读取 `original_report`，不把同文件中删除亏损后的事后统计登记为策略收益。

原有全文证据搜索继续可用：`catalog refresh` 更新摘录，`catalog search "ETH 55 31"` 查询。JSON 摘录继承所属对象的配置，不会把邻近版本的参数拼成同一条证据。

诊断从已保存的权益、交易和事件读取，不重新运行策略：

```powershell
.\venv\Scripts\python.exe -m scripts.research_cli backtest diagnostics 运行编号
.\venv\Scripts\python.exe -m scripts.research_cli backtest diagnostics 运行编号 --equity-kind execution_equity
.\venv\Scripts\python.exe -m scripts.research_cli backtest trade-timeline 运行编号 交易编号
.\venv\Scripts\python.exe -m scripts.research_cli backtest trade-changes 原运行编号 对照运行编号 --offset 0 --limit 100
```

页面在已完成回测详情中提供「账户与交易诊断」，点击逐笔交易后可读取其过程。连续账户年/月收益以 UTC 收盘权益为基础，包含持仓浮盈和实际仓位；在缺少边界采样时沿用边界前的最后权益并标出记录时间。它与按平仓年月分组的已实现盈亏贡献分开显示。细周期曲线缺失时明确返回不可用，不用主周期曲线代替。

回撤列出高点、谷底、恢复时刻、持续时间及结束时仍未恢复的区间。等额统计按每笔同样本金换算全部交易的毛利、毛亏及盈利集中度，不把它当作重新模拟的账户收益。

两版交易按准确开仓时间、方向和同刻次序匹配。输出新增、减少、改变和未变交易；同时显示少做的亏损、错过的盈利和新增交易的盈亏。价格和收益率忽略 `1e-12` 级浮点误差，时间不允许近邻匹配。单次交易过程只展示已保存信号、事件和成交。旧版本没有状态事件时保留这一限制，不推测当时为何等待或拒绝反手。

HTTP 与 CLI 共用相同服务。对应接口为 `POST /api/v1/research-results/query`、`POST /api/v1/research-results/refresh`、`GET /api/v1/research-results/{entry_id}`，以及 `GET /api/v1/local-backtests/{run_id}/diagnostics`、`trade-timeline/{trade_id}`、`trade-changes/{other_id}`。

交易过程同时展示同次决策发出的平仓与突破委托；平仓后未触及突破价或超过追价上限，不会遗漏为无法解释的未反手。若成交使用细周期，委托检查覆盖退出所在的完整信号周期。相关决策根已保存的指标值和布尔条件也一并显示；没有记录的条件不会推测补全。
