# OpenTrading

<!-- impeccable:product-schema 1 -->

## Platform

web。当前在 Windows 上验收，已有 Vue 3 / TypeScript 前端与 Python API。

## Product Purpose

OpenTrading 提供行情图表、策略研究、投资组合分析和交易产品目录。股票页的现有任务是查找底层股票或 ETF，对比 Binance、OKX、Bitget 的已核实产品覆盖，并打开具体产品的官方页面。

## Workflows and Evidence

股票目录来自既有 `/api/v1/equities/catalog` 接口；每行合并同一证券的产品，搜索支持代码、中英文名称和产品代码。平台与交易方式筛选必须匹配同一产品。页面不提供股票实时价格或成交能力证明。

## Constraints

用户已确认股票页的三种布局，并授权将按任务切换布局的方式推广到币安行情、Web3 榜单、市场指标、资产对比、定投、组合及图表工作台。设置、数据健康和减半周期保留各自的默认结构，改善分区、操作入口及信息层级。保留既有数据、产品链接、来源覆盖说明、深浅主题和中英文能力。Bitget Stock+ 完整名单未核实，缺少某平台记录不能解释为该平台不支持。不得虚构行情、价格、涨跌幅或交易能力。

## Open Decisions

各页面使用适合自身任务的布局，保留既有品牌、业务接口和计算口径。布局偏好独立保存，切换布局保留当前筛选、选择、输入和已有结果。
