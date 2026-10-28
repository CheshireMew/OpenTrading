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
---

# Design System: OpenTrading

## Overview

本文件记录已实现的界面，依据共享调色板、全局样式、应用导航、交易对搜索和图表工作台。OpenTrading 用于行情图表、策略研究与投资组合分析；界面以图表、表格和配置表单为主，保留现有品牌与布局。

深色界面以石墨灰承载内容，青绿色标示主要操作和当前状态；浅色界面使用暖白背景与墨绿色重点。品牌字标使用衬线字体，操作界面使用系统无衬线字体。内容区域主要依靠底色、细边框和间距划分。

**Key Characteristics:**

- 深浅主题共享语义颜色，应用外壳与通用页面使用同一套运行时变量。
- 研究页面保持清楚的标题、配置、结果层次；图表工作台保留紧凑的工具密度。
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

## Layout

应用占满窗口高度，主内容区独立滚动。普通页面在桌面保留固定侧栏（224px），窄屏切换为覆盖式菜单（288px）；图表首页始终通过菜单按钮打开覆盖式导航。

通用页面使用完整可用宽度，内边距与区域间距沿用 spacing.6。窗口宽度不超过现有阈值（767px）时，页面内边距改为纵向 spacing.5、横向 spacing.3，较大的介绍容器也缩小内边距。

研究与投资工具根据主内容容器宽度调整网格，而不只依赖窗口宽度。现有容器阈值为 34rem、56rem 和 100rem；组合配置另有 46rem 阈值。响应式数据表在容器不超过 60rem 时转为带字段名称的两列数据块，主要字段横跨整行。

图表工作台由顶部工具栏、主图、自选列表和底部编辑区域组成。自选列表桌面可调宽（240–520px）；窗口不超过 950px 时成为覆盖式抽屉。较窄工具栏与底部标签允许横向滚动，搜索筛选和编辑操作允许换行，长交易对名称可折行。

## Elevation & Depth

普通卡片通过底色与细边框形成层次，不添加通用卡片投影。投影用于临时覆盖的菜单、搜索弹窗、指标面板和抽屉，遮罩用于将其与背景区分。具体投影保存在 sidecar，避免把弹窗投影用于常驻内容。

常规控件使用短过渡，侧栏使用滑入滑出过渡。系统启用减少动态效果时，现有全局规则将动画与过渡压缩至近乎即时，不增加额外运动。

## Shapes

卡片和通用面板使用 panel 圆角，按钮和常规输入使用 control 圆角，编辑器内部容器和图表外框使用 inset 圆角，标签和分段按钮使用 chip 圆角。交易对搜索弹窗保留独立的 symbol-dialog 圆角；图表工作台搜索与命名弹窗沿用 panel 圆角。

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

### Don't:

- **Don't** 将图表工作台的紧凑控件尺寸直接用于普通页面表单。
- **Don't** 将临时弹窗和抽屉的投影复制到常驻卡片。
- **Don't** 将局部硬编码色值当作新的全局主题色。

<!-- Evidence: frontend/src/theme/palette.mjs; frontend/tailwind.config.js; frontend/src/style.css; frontend/src/App.vue; frontend/src/components/SymbolSearchBox.vue; frontend/src/views/ChartWorkspace.vue; frontend/src/composables/useModalDialog.ts; README.md. -->
