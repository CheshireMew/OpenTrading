---
name: OpenTrading
description: 行情图表、策略研究与投资组合分析工具的现有界面规范。
colors:
  light-canvas: "#f7f4ed"
  light-panel: "#ffffff"
  light-toolbar: "#fbfaf7"
  light-elevated: "#f1eee7"
  light-hover: "#eae7df"
  light-border: "#e4ded3"
  light-border-strong: "#b8b2a8"
  light-grid: "#ece8df"
  light-text: "#383b36"
  light-title: "#18251f"
  light-muted: "#65645d"
  light-faint: "#746e65"
  light-accent: "#0f6b4f"
  light-accent-hover: "#0b5a41"
  light-positive: "#087e68"
  light-negative: "#c52d3c"
  light-blue: "#2868c8"
  dark-canvas: "#151619"
  dark-panel: "#1b1d23"
  dark-toolbar: "#15181e"
  dark-elevated: "#22252d"
  dark-hover: "#292c34"
  dark-border: "#2a2b30"
  dark-border-strong: "#434651"
  dark-grid: "#24262d"
  dark-text: "#d1d4dc"
  dark-title: "#f0f3fa"
  dark-muted: "#959ca9"
  dark-faint: "#8992a2"
  dark-accent: "#22ab94"
  dark-accent-hover: "#1c9580"
  dark-positive: "#089981"
  dark-negative: "#f23645"
  dark-blue: "#5086f5"
  dark-on-accent: "#09231f"
  dark-nav-active: "#73cabb"
typography:
  brand:
    fontFamily: 'Georgia, "Times New Roman", serif'
  body:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif'
  title:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif'
    fontSize: "26px"
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: "-0.025em"
  section:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif'
    fontSize: "16px"
    fontWeight: 600
    lineHeight: 1.5
  subtitle:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif'
    fontSize: "14px"
    lineHeight: "24px"
  label:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif'
    fontSize: "12px"
    fontWeight: 600
    lineHeight: "16px"
rounded:
  chip: "4px"
  control: "5px"
  inset: "6px"
  panel: "8px"
  symbol-dialog: "10px"
spacing:
  "1": "4px"
  "2": "8px"
  "3": "12px"
  "4": "16px"
  "5": "20px"
  "6": "24px"
components:
  button-primary:
    backgroundColor: "{colors.light-accent}"
    textColor: "{colors.light-panel}"
    rounded: "{rounded.control}"
    padding: "8px 16px"
  button-primary-hover:
    backgroundColor: "{colors.light-accent-hover}"
  button-primary-dark:
    backgroundColor: "{colors.dark-accent}"
    textColor: "{colors.dark-on-accent}"
    rounded: "{rounded.control}"
    padding: "8px 16px"
  button-primary-dark-hover:
    backgroundColor: "{colors.dark-accent-hover}"
  button-secondary:
    backgroundColor: "{colors.light-toolbar}"
    textColor: "{colors.light-text}"
    rounded: "{rounded.control}"
    padding: "8px 16px"
  button-secondary-dark:
    backgroundColor: "{colors.dark-toolbar}"
    textColor: "{colors.dark-text}"
    rounded: "{rounded.control}"
    padding: "8px 16px"
  button-danger:
    textColor: "{colors.light-negative}"
    rounded: "{rounded.control}"
    padding: "8px 12px"
  input:
    backgroundColor: "{colors.light-toolbar}"
    textColor: "{colors.light-text}"
    rounded: "{rounded.control}"
    padding: "8px 12px"
  nav-link:
    textColor: "{colors.light-text}"
    rounded: "{rounded.chip}"
    padding: "8px 12px"
  chip:
    backgroundColor: "{colors.light-elevated}"
    textColor: "{colors.light-text}"
    typography: "{typography.label}"
    rounded: "{rounded.chip}"
    padding: "4px 12px"
  card:
    backgroundColor: "{colors.light-panel}"
    textColor: "{colors.light-text}"
    rounded: "{rounded.panel}"
    padding: "20px"
  symbol-trigger:
    backgroundColor: "{colors.light-toolbar}"
    rounded: "{rounded.control}"
    padding: "0 12px"
  task-tab:
    textColor: "{colors.light-muted}"
    padding: "8px 0 12px"
  task-tab-active:
    textColor: "{colors.light-accent}"
---

# Design System: OpenTrading

## 页面布局切换

布局选择器使用带图标、文字和按下状态的原生按钮组，选中项使用主题重点色。每页提供与任务对应的视图，不规定统一的布局数量。行情页面可在表格、列表与详情及侧栏筛选间选择；指标在图表概览与紧凑列表间选择；对比图表可调整主次或单图放大；定投可收起配置；组合增加总览和单项资产详情。图表工作台通过独立面板栏切换图表、自选和编辑器，保留原有主图状态。

列表与详情在宽区域按 280px 列表与弹性详情区排列，窄区域上下排列。详情复用现有内容和数据；内嵌时不使用浮层遮罩与焦点锁定。选中行通过底色与左侧色线提示，重复点击可收起。完整页面行为与数据口径见 `docs/UI_LAYOUTS.md`。

## Overview

本文件记录已实现的界面，依据共享调色板、全局样式、应用导航、行情列表、研究工作台和投资工具。OpenTrading 用于行情图表、策略研究与投资组合分析；界面以图表、表格和配置表单为主，在现有品牌下按当前任务组织内容。

深色界面以石墨灰承载内容，青绿色标示主要操作和当前状态；浅色界面使用暖白背景与墨绿色重点。品牌字标使用衬线字体，操作界面使用系统无衬线字体。内容区域主要依靠底色、细边框和间距划分。

**Key Characteristics:**

- 深浅主题共享语义颜色，应用外壳与通用页面使用同一套运行时变量。
- 行情与组合页面通过任务标签页分开操作，指标条、表格和主图各有清楚的层次；图表工作台保留紧凑的工具密度。
- 研究从建清单、加资产到查看详情逐步展开，数据健康先显示需要处理的来源，设置按用途分区。
- 键盘焦点、弹窗关闭与焦点恢复具有明确反馈。

## Colors

### Primary

浅色的墨绿与深色的青绿用于主要按钮、选中项、焦点轮廓和输入光标。悬停使用各主题对应的 accent-hover。深色实心按钮使用专门的深色文字，深色导航选中项使用较亮的青绿文字。

### Secondary

positive、negative 与 blue 是已有的数据语义色，分别用于正负变化与蓝色数据表达。它们保留各主题的独立取值，不能与主要操作色互换。

### Neutral

canvas 承载页面，panel 承载内容容器，toolbar 承载工具栏与输入背景。elevated 和 hover 区分层次及悬停；border 和 border-strong 分别用于内容分界与控件轮廓。title、text、muted、faint 依次承担标题、正文、辅助信息与占位文字，grid 用于图表网格。

共享颜色来自 `frontend/src/theme/palette.mjs`，由 Tailwind 注入 `--ui-*` 变量。现有灰阶工具类也映射到主题中性色。

**The Theme Token Rule.** 通用界面沿用现有语义变量，深浅主题一起维护；图表工作台的局部色值不升级为通用调色板。

## Typography

品牌字标沿用 Georgia 衬线字体；正文、按钮、输入、导航与图表工作台沿用系统字体栈，Windows 下优先使用 Segoe UI 和 Microsoft YaHei。品牌在侧栏、移动标题栏及图表栏使用不同字号，不定义新的大标题展示字体。

页面标题使用 title，窄屏缩小为现有字号（23px）。分区标题使用 section，说明文字使用 subtitle，表单标签使用 label。侧栏导航采用紧凑字号（13px），图表工作台基础文字更紧凑（12px）；这些是局部密度设置，不替代页面正文。

说明文字限制行长（75ch），并允许长内容换行。通用容器内的数据单元格、定义列表值和输出使用等宽数字，便于纵向比较。

共享指标条的标签更轻、更小（12px），数值使用半粗字与紧凑行高（24px、600、1.2）。定投结果数值在局部缩小（22px；最窄容器下为19px），不改变通用标题层级。

## Layout

应用占满窗口高度，主内容区独立滚动。普通页面在桌面保留固定侧栏（224px），窄屏切换为覆盖式菜单（288px）；图表首页始终通过菜单按钮打开覆盖式导航。

普通页面内容在可用区域内居中，最大宽度为（1760px），桌面内边距为（28px 32px 40px），区块间距沿用 spacing.6。普通与 wide 两种页面容器目前共享这些值。窗口宽度不超过现有阈值（767px）时，页面内边距改为纵向 spacing.5、横向 spacing.3，较大的介绍容器也缩小内边距。

主内容建立命名容器，研究、投资工具、筛选和设置根据该区域的实际宽度重排。设置分区与股票筛选在容器不超过（48rem）时收为单列分区或折叠筛选；定投在容器至少（68rem）时成为配置侧栏与结果主区；研究详情在至少（60rem）时与资产列表并列，在至少（88rem）时再将清单展开为左栏。局部规则保留各自阈值，不把某个页面的栏宽用作通用网格。

响应式数据表拥有自己的宽度容器，在不超过（60rem）时转为带字段名称的两列记录，主要字段横跨整行；股票展开的产品明细接在对应记录下。表格在较宽区域保留列标题、排序和横向滚动，通用数据表单元格的纵向内边距为（12px）。

图表工作台由顶部工具栏、主图、自选列表和底部编辑区域组成。自选列表桌面可调宽（240–520px）；窗口不超过 950px 时成为覆盖式抽屉。较窄工具栏与底部标签允许横向滚动，搜索筛选和编辑操作允许换行，长交易对名称可折行。

## Elevation & Depth

普通卡片通过底色与细边框形成层次，不添加通用卡片投影。投影用于临时覆盖的菜单、搜索弹窗、指标面板和抽屉，遮罩用于将其与背景区分。具体投影保存在 sidecar，避免把弹窗投影用于常驻内容。

常规控件使用短过渡，侧栏使用滑入滑出过渡。系统启用减少动态效果时，现有全局规则将动画与过渡压缩至近乎即时，不增加额外运动。

任务标签页的文字与底线、指标快捷筛选的背景使用短过渡（160ms ease）。加载骨架使用缓慢透明度脉动（1.6s ease-in-out、alternate），减少动态效果仍由同一全局规则控制。

## Shapes

卡片和通用面板使用 panel 圆角，按钮和常规输入使用 control 圆角，编辑器内部容器和图表外框使用 inset 圆角，标签和分段按钮使用 chip 圆角。交易对搜索弹窗保留独立的 symbol-dialog 圆角；图表工作台搜索与命名弹窗沿用 panel 圆角。任务标签页使用平直底线，与实心分段按钮区分。

常规容器与输入使用细实线边框。选中导航通过左侧色线与浅色底提示位置，选中自选行通过内侧色线提示位置，不依靠增大圆角或投影表示选中。

## Components

### Buttons

主按钮使用主题重点色，次按钮使用工具栏底色与较强边框，危险按钮使用负向色描边与文字。通用按钮和输入的桌面最小高度一致（38px）；窄屏或触摸指针环境增加到现有触控高度（44px）。分段按钮默认更紧凑（36px），移动环境沿用触控高度。

主按钮悬停加深背景，次按钮悬停使用 hover 背景并加强边框。禁用按钮保留已有降低透明度和禁用光标。焦点使用主题重点色轮廓（2px），普通元素外移 3px，表单控件外移 1px。

### Chips

标签使用 elevated 底色、正文色、label 字号和 chip 圆角，内边距沿用 spacing.1 与 spacing.3。分段选择器的选中项使用实心重点色；它与仅展示分类的标签承担不同状态。

### Cards / Containers

普通卡片使用 panel 底色、border 细边框、panel 圆角与 spacing.5 内边距。较大的介绍容器使用 spacing.6，面板标题使用纵向 spacing.4、横向 spacing.5。编辑区域内部容器更紧凑，沿用 spacing.3。

### Inputs / Fields

输入与选择器使用 toolbar 底色、border-strong 边框和 control 圆角。占位文字使用 faint，焦点同时改变边框与轮廓；禁用输入使用 canvas 底色与 faint 文字。选择框与单选框、复选框保留原生操作方式，并使用主题重点色。

### Navigation

侧栏导航默认使用正文色，悬停使用 elevated 底色与标题色，当前路由显示重点色左线、混合浅底与更粗文字。移动菜单与图表页覆盖式导航打开后，主内容暂时退出交互；关闭后恢复原焦点。跳转到主内容的链接在键盘聚焦时显示。

研究各页面共用横向路由导航，当前位置以重点色文字和底线表达。导航允许横向滚动，链接保持现有触控高度（44px），窄屏内边距与普通页面一致。

### Task Tabs / Metric Strips

任务标签页用于同一页面内的不同工作，默认文字使用 muted，选中时使用重点色文字与底线（2px），不使用实心按钮底。标签页最小高度为（46px），项目间距为（24px；容器不超过48rem时为20px），内容超宽时横向滚动。可选计数使用小标签。共享组件维护 tablist、tab、tabpanel 的关联，支持左右方向键循环切换以及 Home、End 定位，并将焦点移至新选中项。

指标条通过上下边框组织摘要，默认按可用宽度分配列，容器不超过（48rem）时为两列。股票统计项同时作为快捷筛选，使用按下状态、混合浅底和重点色文字显示当前筛选；纯展示指标仍使用定义列表。

### Empty / Loading States

共享空态以标题、可选说明、可选图标和下一步操作组成，不填充虚构数据。内容居中，最小高度为（220px），内边距为（40px 24px），说明最大宽度为（36rem）；操作允许换行。

共享加载态保留列表轮廓，默认五行，每行三段骨架（2fr 1fr 1fr），行高至少（64px）。骨架对辅助技术隐藏，通过 status、polite 提供加载文字。已有结果刷新时，页面可保留内容并显示忙碌状态；首次加载使用骨架，失败使用页内反馈与已有重试入口。

### Market Lists

币安行情先展示摘要和刷新操作，再通过监控、排行榜两个任务页切换；排行榜内继续区分合约与现货。监控筛选、排序、交易对详情与自动刷新保留各自作用，表格复用响应式记录布局。

股票页面以可点击统计条、搜索、精细筛选和结果列表组织任务。宽区域的筛选栏保留在结果上方，窄容器下通过筛选按钮展开，按钮显示已选条件数；空结果提供现有的清除筛选操作。产品明细按行展开，来源说明放在折叠区域。Web3 页面共用链选择，通过热度榜与地址表现两个任务页分别呈现表格。

### DCA Workspace

定投将配置、市场参考与计算结果分开。宽容器下左栏固定为（320px），与结果区间距为（28px），配置栏在滚动时保持距顶（24px）；较窄时上下排列。执行时间与时区放在默认折叠的执行设置内，计算操作位于表单末尾。

结果先显示六项指标，再以收益率趋势作为主图（320px 高），价格与成本、每日金额作为两张辅助图（各256px高）。辅助图只在宽容器下并排，不把三张图设成同等层级。没有结果时显示计算引导，首次计算时显示骨架。

### Portfolio Workspace

组合选择采用页面上方的横向选择器与新建操作；导入、导出、复制、删除与回收站收在管理折叠区。组合内容分为目标配置、流水与业绩、历史模拟、风险与情景四个任务页，存储与来源反馈在这些任务之间共享。没有持仓时，配置页提供进入账本的下一步操作。

配置页先呈现资产与权重，组合名称、日期和再平衡参数收在默认折叠的设置内。历史模拟结果的指标按四列展示，容器不超过（48rem）时改为两列。风险页首次进入后再加载；已有持仓时呈现收益与风险指标、净值、风险贡献和相关性，情景测试按实际资产逐项输入冲击幅度。无持仓、加载和错误保持独立反馈。

### Data Health / Settings

数据健康先显示总状态、待处理来源数、来源总数与数据库版本，再展开全部非 ready 来源及其可执行操作；ready 来源收在默认折叠的列表里。历史补全保留独立表单，后台任务另行折叠。来源修复若需要交易对参数，先定位并聚焦对应表单。表单在容器不超过（48rem）时变为两列，不超过（28rem）时变为单列。

设置按偏好、模型配置、运行环境三个用途分区。宽区域使用左侧标题与说明、右侧控件的布局（minmax(180px, .65fr) 与 minmax(0, 2fr)），列间距为（48px）；容器不超过（48rem）时改为上下排列。分区通过间距和细分隔线组织，模型与运行环境保留各自的加载、错误和重试反馈。

### Symbol Search / Dialogs

交易对搜索由触发按钮、标题、搜索框、资产筛选与结果列表构成。搜索框通过整个边框区域显示焦点，结果在窄屏分为两列，较宽时转为四列。弹窗限制高度并让结果区滚动，加载、失败和无结果各有现有反馈。

共用弹窗逻辑将焦点限制在最上层弹窗；Escape 只关闭最上层，关闭后恢复触发位置。搜索、命名、兼容说明、导航与自选抽屉复用该行为。

### Chart Workspace

图表工作台保留原有高密度控件，默认最小高度（28px）与窄屏工具栏高度（36px）有别于通用表单。深色工作台映射共享主题，浅色工作台仍有独立局部颜色；该既有差异不作为新页面的通用颜色依据。

## Do's and Don'ts

### Do:

- **Do** 使用共享语义变量同步维护通用页面的深浅主题。
- **Do** 保留 Georgia 品牌字标与系统界面字体的职责分工。
- **Do** 保留可见焦点、弹窗内 Tab 循环和关闭后的焦点恢复。
- **Do** 按现有容器宽度重排表格与网格，让内容区独立滚动。
- **Do** 通过任务标签页、折叠设置与渐进空态保持当前工作的层次，并保留对应下一步操作。

### Don't:

- **Don't** 将图表工作台的紧凑控件尺寸直接用于普通页面表单。
- **Don't** 将临时弹窗和抽屉的投影复制到常驻卡片。
- **Don't** 将局部硬编码色值当作新的全局主题色。

<!-- Evidence: frontend/src/theme/palette.mjs; frontend/tailwind.config.js; frontend/src/style.css; frontend/src/App.vue; frontend/src/components/AppTabs.vue; frontend/src/components/AppEmptyState.vue; frontend/src/components/AppLoadingState.vue; frontend/src/components/research/ResearchNavigation.vue; frontend/src/components/SymbolSearchBox.vue; frontend/src/views/ChartWorkspace.vue; frontend/src/views/indicators/BinanceMarket.vue; frontend/src/views/indicators/EquityMarket.vue; frontend/src/views/indicators/Web3MarketRank.vue; frontend/src/views/tools/DCA.vue; frontend/src/views/tools/PortfolioBalance.vue; frontend/src/components/portfolio/PortfolioBalanceSidebar.vue; frontend/src/components/portfolio/PortfolioBalanceSetup.vue; frontend/src/components/portfolio/PortfolioSimulationPanel.vue; frontend/src/components/portfolio/PortfolioRiskPanel.vue; frontend/src/views/research/ResearchWorkbench.vue; frontend/src/views/system/DataHealth.vue; frontend/src/views/settings/Settings.vue; frontend/src/composables/useModalDialog.ts; README.md. -->
