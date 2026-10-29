---
version: 1
slug: "frontend-src-views-indicators-equitymarket-vue"
primary_target: "frontend/src/views/indicators/EquityMarket.vue"
related_targets: []
---

# 股票目录三种布局

范围：`/indicators/equities`，Operate；Windows 浏览器。用户明确要求“把这3个布局都实现一下，可以通过某个按钮切换布局”，并要求不用子 Agent。

## Direction contract

THESIS: 同一份真实证券目录提供逐证券查看、平台横向比较、常驻条件筛选三种操作方式；以布局切换替代三份状态互不相通的页面。

OWN-WORLD: 沿用全局导航、Georgia 字标、暖白墨绿及石墨青绿双主题。页面采用32px标题、清晰搜索、细分隔线、紧凑证券行；平台语义由列和分组承载，取消重复彩色徽章堆叠。

STORY: 搜索代码或名称，按同一产品的平台与交易方式筛选，查看证券的具体产品，打开原有官方链接。切换布局保留条件、页码和所选证券；布局偏好在本机保存。

FIRST VIEWPORT: 页首标题与刷新、三按钮布局选择；搜索位于其下。双栏是紧凑证券列表与按平台分组的详情；对照模式是证券列加三平台列，就地展开产品；筛选模式是常驻筛选栏与证券目录。窄屏按任务顺序重排，保留三个切换按钮。

FORM: 用户选择同时实现 seed:cf8e2ce1058abb39 中呈现的三种构图；code-led。`.impeccable/mocks/decision/equities-master-detail.html`、`equities-coverage-matrix.html`、`equities-filter-directory.html` 是结构参考，用户新指令优先于单选流程。

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

验收：三种真实布局、切换状态保留、搜索/筛选/排序/分页、产品展开及链接、来源状态、错误与空态；桌面/窄屏、中英文、双主题。只检查当前股票页相关行为，不扩展到其他功能。按用户要求，收尾评审与文档核对由主线程执行。
