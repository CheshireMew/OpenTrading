# OpenTrading

<!-- impeccable:product-schema 1 -->

## Platform

web。当前在 Windows 上验收，已有 Vue 3 / TypeScript 前端与 Python API。

## Product Purpose

OpenTrading 提供行情图表、策略研究、投资组合分析和交易产品目录。股票页的现有任务是查找底层股票或 ETF，对比 Binance、OKX、Bitget 的已核实产品覆盖，并打开具体产品的官方页面。

## Workflows and Evidence

股票目录来自既有 `/api/v1/equities/catalog` 接口；每行合并同一证券的产品，搜索支持代码、中英文名称和产品代码。平台与交易方式筛选必须匹配同一产品。页面不提供股票实时价格或成交能力证明。

## Constraints

本次用户确认先在股票页尝试完整视觉改版，并要求将双栏、平台对照、左侧筛选三种布局全部实现，用按钮切换后比较效果；其他路由不随之改版。保留既有数据、产品链接、来源覆盖说明、深浅主题和中英文能力。Bitget Stock+ 完整名单未核实，缺少某平台记录不能解释为该平台不支持。不得虚构行情、价格、涨跌幅或交易能力。

## Open Decisions

股票页的试验结果尚未确认为全站视觉规范；是否推广到其他页面由用户后续决定。
