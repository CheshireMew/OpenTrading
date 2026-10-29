# 股票市场目录

入口：市场指标 → 股票市场，路径 `/indicators/equities`。

页面以底层股票为一行，合并交易所支持标签及「现货」「永续合约」标签；展开后显示各平台具体产品、交易代码、交易状态和官网链接。股票代币、券商股票都归入现货，杠杆和反向股票 ETF 仍是独立标的，不合并到被跟踪的股票。搜索支持代码、官方名称、产品代码及常用股票中文名称。

股票代码旁展示公司 Logo。对接口缺失的公司手动核对并补充本地图标，映射保存在 `app/services/market/equity_logo_overrides.py`，图片及来源记录位于 `frontend/public/equity-logos/`；同一公司的不同产品代码共用公司图标，基金与指数使用发行方或指数提供方标识。2026-10-17 已补齐当时缺失的 158 个代码。其余使用币安股票静态目录的 `l` / `logo` 字段，保留实际文件名与后缀，并按底层证券合并到各平台产品；没有公司 Logo 时可使用 Alpha 返回的图标。图片只在接近可见区域时加载，保持原始比例；新标的暂缺图片或加载失败时显示股票代码缩写。

## 页面布局

页面右上角可切换“双栏”“平台对照”“左侧筛选”。双栏并排显示证券列表和产品详情；平台对照按 Binance、OKX、Bitget 分列，点击证券或任意平台单元格即可展开、收起产品详情，具体产品链接上的斜箭头表示前往官方页面；左侧筛选将条件常驻在目录旁，窄屏通过“筛选”按钮展开。

三种布局共用搜索、平台、交易方式、标的类型、跨平台条件、排序、页码和所选证券，切换时不会重新请求目录。布局偏好保存在当前浏览器，刷新后恢复；搜索与筛选条件只在本次页面使用期间保留。产品链接、来源状态和覆盖限制共用原有接口。


## 数据来源

目录由后端实时读取，不使用手写的热门股票名单，不截取前 N 个产品。

| 来源 | 公开目录 |
| --- | --- |
| Binance Stocks | `www.binance.com/bapi/equity/v2/public/equity/symbol/get-exchange-info`，配合 `get-symbols-static` 名称和类型 |
| Binance bStocks | `www.binance.com/bapi/asset/v2/public/asset-service/product/get-products?includeEtf=true` 中带 `bStocks` 标签的产品 |
| Binance Alpha | `www.binance.com/bapi/defi/v1/public/wallet-direct/buw/wallet/cex/alpha/all/token/list` 中标记为股票且未下架的产品 |
| Binance 永续 | `fapi.binance.com/fapi/v1/exchangeInfo` 中股票、盘前股票分类的永续合约 |
| OKX 现货和永续 | `www.okx.com/api/v5/public/instruments?instType=SPOT` / `SWAP`，股票分类 `instCategory=3` |
| Bitget Reality / 股票代币现货 | `api.bitget.com/api/v3/market/instruments?category=SPOT`，股票分类和 `isReality` 标记 |
| Bitget 股票永续 | 同一接口的 `USDT-FUTURES`、`USDC-FUTURES`、`COIN-FUTURES`，保留股票分类且 `type=perpetual` |

**覆盖限制：Bitget Stock+ 的完整可交易名单尚未获取并核实，未纳入支持判断。** 页面明确展示这项缺口；不能从缺少 Bitget 标签推断 Stock+ 不支持，也不能把所有美股直接视为 Bitget 支持。

2026-10-17 核查了[官方 Stock+ 股票行情文档](https://www.bitget.com/zh-CN/docs/catalog/stock-plus/stock-quotes)：`GET /api/v3/stockplus/market/static` 可查基本资料，`GET /api/v3/stockplus/market/quote` 可查报价，均须提供已知股票代码（例如 `AAPL.US`），单次最多 500 个，并要求「Stock+ 行情（只读）」权限。无凭证实际请求基本资料接口返回 HTTP 400、`code=40006`、`Invalid ACCESS_KEY`。这些接口说明有程序化获取资料的方式，但文档未列出全量可交易名单接口，返回行情也不能单独证明可下单。

同时核对了官方 [Agent SDK](https://github.com/Bitget-AI/agent-sdk) 的接口目录，并实际调用[官方美股 MCP](https://www.bitget.com/docs/uta/agent-hub) 的工具目录：SDK 当前目录不含 Stock+ 接口；MCP 提供美股行情、基本面和 ETF 资料，未发现 Stock+ 可交易名单入口。另有 [Bitget Wallet RWA 全量列表接口](https://web3.bitget.cloud/en/docs/market/rwa)，但它返回链上股票代币及合约映射，不能当成 Stock+ 名单。上述结果表示当前尚未找到完整目录获取方式，不表示平台不存在其他内部或授权接口。

股票 ETF 保留，明确的实物贵金属、原油、债券、波动率和加密资产基金排除。平台分类存在边界差异，页面同时保留官方类型和「待分类」。测试产品剔除。部分停牌或限制交易的产品保留并标示「交易受限」，已经下架的记录不计入。

同一证券的不同计价币归到同一行，产品明细仍逐项保留。伯克希尔 B 类等明确代码别名合并；不同股权类别和韩国原股 / 美国 ADR 不合并。交易所新增代码不依赖本地名单才能出现。

部分合约为避免与加密代币重名而使用特殊代码，按官方公告对齐底层证券：[STXX → STX](https://www.binance.com/en/support/announcement/detail/f622c1f2a1a94ba1894d9a9e265fb4b9)、[QNTX → QNT](https://www.binance.com/en/support/announcement/detail/3bdaff694bde45ccb443709336c8686d)、[USDEX → USDE](https://www.binance.com/en-ZA/support/announcement/detail/ea19450f515843098a5d5e55fc6e3589)。STXX 在真实股票目录里也是一个独立 ETF，因此该别名只作用于币安永续合约。PAYP（PayPay）与 PYPL（PayPal）保持为两个标的。

## 接口与刷新

`GET /api/v1/equities/catalog?refresh=false` 返回 `items`、`sources`、`updated_at` 和 `complete`，并由项目现有生成器生成前端契约。

目录缓存 5 分钟，手动刷新绕过本轮缓存，并发刷新共用一次请求。每个来源独立保存上次成功结果；新请求失败时保留旧数据并标记 `stale`，首次失败标记 `unavailable`，不伪装成空目录。若缓存服务可用，上次来源结果保存 24 小时。`complete` 只有在所有已声明来源均成功时才为真；Stock+ 未能读取期间保持为假。

平台筛选与交易方式筛选必须匹配同一个产品。例如，币安仅有现货、OKX 仅有永续的股票不能在「币安 + 永续合约」条件下出现。

股票产品链接和来源详情中的官网页面统一附带站主邀请码：Binance `ref=SRXT5KUM`，OKX `channelId=A999998`，Bitget `clacCode=W76TDL38`。保留具体股票路径、其他查询参数和页面锚点；在目录合并时处理，因此缓存中的旧链接也会附带当前邀请码。行情 API 请求及来源详情中的原始 API 链接保持原样。

2026-10-17 核对了 OKX 官网页面对 `channelId` 的读取逻辑及[邀请页](https://www.okx.com/join/A999998)返回的渠道信息；Bitget 实测从带 `clacCode` 的股票交易页点击注册，注册表单自动填入 `W76TDL38`。参见 [Bitget 官方邀请链接说明](https://www.bitget.com/support/articles/12560603884092)。邀请归属由平台在新用户注册时确认，已有账号不会仅因点击链接而改变归属；本次未实际注册账号。

验证：`python -m pytest -q test/test_equity_catalog.py`，以及 `npm --prefix frontend run typecheck`。当前只验收 Windows。
