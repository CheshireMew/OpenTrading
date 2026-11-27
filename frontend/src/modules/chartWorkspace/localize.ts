import { watch } from 'vue'
import i18n from '@/i18n'
import { cw, messageText, workspaceMarketLabel, symbolName } from './locale'
import type { ChartSymbol } from './api'

// Vela 0.7.6 exposes English chrome but no locale option. Keep the translation
// boundary outside its renderer; scripts, prices and the attribution stay intact.
const vocabulary:Record<string,string>={
  'Reset chart view':'重置图表视图','Reset view (all history)':'重置视图（全部历史）','Remove indicators':'移除指标','Settings…':'设置…','More settings…':'更多设置…',
  'Show chart':'显示图表','Hide chart':'隐藏图表','Symbol logo':'品种图标','Symbol name':'品种名称','Market status':'市场状态','OHLC values':'开高低收','Bar change values':'K 线涨跌','Indicator values':'指标数值',
  'Titles':'名称','Values':'数值','Open':'开盘','High':'最高','Low':'最低','Price':'价格','Date':'日期','Time':'时间','Interval':'周期','Session':'交易时段',
  'Layout':'布局','Single':'单图','Sync':'同步','Timeframes':'周期','Change timeframe':'切换周期','Extended hours':'延长交易时段','Trading session':'交易时段','Pre-market':'盘前','Post-market':'盘后',
  'Session — regular (RTH) vs extended (ETH) hours':'交易时段：常规时段（RTH）或延长时段（ETH）','Bars to fetch':'历史根数',
  'Auto (fits data to screen)':'自动（适应屏幕）','Toggle logarithmic scale':'切换对数坐标','Toggle percent scale':'切换百分比坐标','Price axis labels':'价格轴标签',
  'Last Price Line':'最新价线','Last price label':'最新价标签','Countdown to bar close':'K 线收盘倒计时','Labels':'标签','Levels':'水平','Mode':'模式','Percent':'百分比','Indexed to 100':'以 100 为基准',
  'Line color':'线条颜色','Top fill':'顶部填充','Bottom fill':'底部填充','Top line':'上方线条','Bottom line':'下方线条','Fill top area':'填充上方区域','Fill bottom area':'填充下方区域','Base level %':'基准位置 %',
  'Pane separator color':'副图分隔线颜色','Vertical':'垂直','Horizontal':'水平','Theme':'主题','Color theme':'颜色主题','Dark':'深色','Light':'浅色','Events':'事件','Visible events':'显示事件',
  'No alerts yet':'暂无警报','No alerts yet.':'暂无警报。','No tools match.':'没有匹配的工具。','Search tools…':'搜索工具…','Search symbol…':'搜索品种…','Search…':'搜索…','Symbol Search':'搜索品种',
  'Add an indicator or a drawing to populate the tree':'添加指标或绘图后，这里会显示对象列表','Remove from chart':'从图表移除','Indicator settings':'指标设置','Add to group':'加入分组','Move to group':'移至分组','Ungroup':'取消分组',
  'Keyboard shortcuts':'快捷键','Show this shortcuts panel':'显示快捷键面板','Undo (active chart)':'撤销（当前图表）','Redo (active chart)':'重做（当前图表）','Drag to move chart':'拖动平移图表',
  'Zoom in':'放大','Zoom out':'缩小','Pan toward history':'向历史方向平移','Pan toward now':'向最新方向平移','Horizontal line at the cursor price':'在光标价格处绘制水平线','Vertical line at the cursor time':'在光标时间处绘制垂直线',
  'Arm the trend line tool':'启用趋势线工具','Open the indicator picker':'打开指标选择器','Scroll to most recent bar (Alt+Shift+→)':'跳到最新 K 线（Alt+Shift+→）',
  'Reset settings':'重置设置','Loading…':'加载中…','In use':'使用中','Chart':'图表','Period':'周期','Periods':'周期数','Offset':'偏移','Upper':'上轨','Lower':'下轨','Basis':'中轨','Multiplier':'倍数','Fill':'填充',
  'Color Up':'上涨颜色','Color Down':'下跌颜色','Axis labels':'坐标轴标签','Scale border color':'坐标轴边框颜色','Background & text':'背景与文字','Text size':'文字大小','Increase':'增加','Decrease':'减少',
  'Bring all to front':'全部置于顶层','Send all to back':'全部置于底层','Move to pane':'移动到副图','New group':'新建分组','Remove indicator':'移除指标','Rename…':'重命名…','Select all':'全选','Show contracts':'显示合约',
  'Scroll to most recent bar':'跳到最新 K 线','Next month':'下个月','Previous month':'上个月','Open calendar':'打开日历','Open time list':'打开时间列表',
  'Up color':'上涨颜色','Down color':'下跌颜色','Direction':'方向','Left':'左侧','Right':'右侧','Start':'开始','Signal':'信号','Histogram':'柱状图','ATR length':'ATR 周期','ATR multiplier':'ATR 倍数',
  'Bollinger multiplier':'布林带倍数','Keltner multiplier':'肯特纳通道倍数','Momentum length':'动量周期','Stop length':'止损周期','Long stop':'多头止损','Short stop':'空头止损','Stop long':'多头止损','Stop short':'空头止损',
  'Rows':'行数','Points':'点数','Depth':'深度','Deviation %':'偏差 %','Factor':'系数','Increment':'增量','Max value':'最大值','Anchor':'锚点','Sections':'分区','Show ratio labels':'显示比例标签','Label…':'标签…','label…':'标签…',
  'Moving Average':'移动平均线','Smoothed Moving Average':'平滑移动平均线','Bollinger Bands':'布林带','Bollinger Bands %B':'布林带 %B','Bollinger Bands Width':'布林带宽度','Moving Average Envelope':'均线包络线',
  'Average Directional Index':'平均趋向指数','Average True Range':'平均真实波幅','Relative Strength Index':'相对强弱指数','Volume Weighted Average Price':'成交量加权均价','Standard Deviation':'标准差',
  'Stochastic':'随机指标','Stochastic RSI':'随机 RSI','SuperTrend':'超级趋势','Parabolic SAR':'抛物线 SAR','Donchian Channels':'唐奇安通道','Keltner Channels':'肯特纳通道','Momentum':'动量',
  'Accumulation / Distribution':'累积 / 派发','On Balance Volume':'能量潮','Money Flow Index':'资金流量指标','Chaikin Money Flow':'蔡金资金流量','Chaikin Oscillator':'蔡金振荡指标','Chaikin Osc':'蔡金振荡',
  'Chaikin Volatility':'蔡金波动率','Chaikin Vol':'蔡金波动率','Choppiness Index':'震荡指数','Commodity Channel Index':'顺势指标','Historical Volatility':'历史波动率','Rate of Change':'变动率',
  'Visible Range Volume Profile':'可视范围成交量分布','Volume Oscillator':'成交量振荡指标','Volume Osc':'成交量振荡','Price Volume Trend':'价量趋势','Volume Flow Indicator':'成交量流向指标',
  'Positive Volume Index':'正量指标','Negative Volume Index':'负量指标','Relative Vigor Index':'相对活力指数','Relative Volatility Index':'相对波动率指数','True Strength Index':'真实强度指数',
  'Linear Regression Curve':'线性回归曲线','Zero-Lag Exponential Moving Average':'零延迟指数移动平均','Variable Index Dynamic Average':'可变指数动态均线','Awesome Oscillator':'动量振荡指标',
  'Force Index':'强力指数','Force':'强力指标','Ease of Movement':'简易波动指标','Balance of Power':'多空力量','Bull power':'多头力量','Bear power':'空头力量','Gator Oscillator':'鳄鱼振荡指标',
  'Williams Alligator':'威廉鳄鱼指标','Williams Fractal':'威廉分形','Williams %R':'威廉 %R','Pivot Points':'枢轴点','Chande Momentum Oscillator':'钱德动量振荡指标','Chande Kroll Stop':'钱德克罗止损',
  'Chandelier Exit':'吊灯止损','Connors RSI':'康纳 RSI','Coppock Curve':'估波曲线','Detrended Price Oscillator':'去趋势价格振荡指标','Fisher Transform':'费舍尔变换','Mass Index':'梅斯线',
  'Percentage Price Oscillator':'价格百分比振荡指标','Percentage Volume Oscillator':'成交量百分比振荡指标','Schaff Trend Cycle':'沙夫趋势周期','Ultimate Oscillator':'终极振荡指标','Vortex Indicator':'涡旋指标','Ulcer Index':'溃疡指数',
  'Jaw':'颚线','Teeth':'齿线','Lips':'唇线','Jaw length':'颚线周期','Teeth length':'齿线周期','Lips length':'唇线周期','Jaw offset':'颚线偏移','Teeth offset':'齿线偏移','Lips offset':'唇线偏移',
  'Point of control':'最大成交量价位','Value area %':'价值区域 %','Volume cap':'成交量上限','Width %':'宽度 %','Height %':'高度 %','Periods per year':'每年周期数','Weeks':'周',
  'Pane height the tallest visible bar occupies':'最高可见柱占副图的高度','Pane width the largest row occupies':'最大成交量行占副图的宽度','Where the accumulation resets (UTC periods)':'累积值重置的周期（UTC）',
  'Annualization factor (365 for daily crypto bars, 252 for stock sessions)':'年化系数（加密货币日线为 365，股票交易日为 252）',
  'Shanghai':'上海','Hong Kong':'香港','Singapore':'新加坡','Tokyo':'东京','New York':'纽约','London':'伦敦','Sydney':'悉尼','Seoul':'首尔','Chicago':'芝加哥','Los Angeles':'洛杉矶',
  'International Date Line West':'国际日期变更线以西','Pago Pago':'帕果帕果','Honolulu':'檀香山','Marquesas Islands':'马克萨斯群岛','Anchorage':'安克雷奇','Phoenix':'菲尼克斯','Denver':'丹佛','Mexico City':'墨西哥城',
  'Bogotá':'波哥大','Caracas':'加拉加斯','Santiago':'圣地亚哥',"St. John's":'圣约翰斯','São Paulo':'圣保罗','Buenos Aires':'布宜诺斯艾利斯','Fernando de Noronha':'费尔南多迪诺罗尼亚','Azores':'亚速尔群岛','Reykjavik':'雷克雅未克',
  'Paris':'巴黎','Berlin':'柏林','Athens':'雅典','Cairo':'开罗','Johannesburg':'约翰内斯堡','Moscow':'莫斯科','Istanbul':'伊斯坦布尔','Tehran':'德黑兰','Dubai':'迪拜','Kabul':'喀布尔','Karachi':'卡拉奇','Mumbai':'孟买','Kathmandu':'加德满都',
  'Dhaka':'达卡','Yangon':'仰光','Bangkok':'曼谷','Eucla':'尤克拉','Adelaide':'阿德莱德','Lord Howe Island':'豪勋爵岛','Nouméa':'努美阿','Auckland':'奥克兰','Chatham Islands':'查塔姆群岛','Apia':'阿皮亚','Kiritimati':'圣诞岛',
  'Maximize pane':'最大化副图','Restore pane':'还原副图','Move pane up':'上移副图','Move pane down':'下移副图','Collapse pane':'收起副图','Expand pane':'展开副图','LINES':'线条','CHANNELS':'通道','Add to favorites':'加入收藏','Remove from favorites':'取消收藏','Main chart':'主图',
  'Group the selected drawings':'将选中绘图分组','Duplicate the selected drawings':'复制选中的绘图','Drag to change what draws in front':'拖动调整图层顺序','Drag to restack, or onto another pane to move it there':'拖动调整顺序或移到另一副图','Drag to another pane, or between panes for a new one':'拖动到其他副图，或拖到副图之间新建',
  'Chart settings':'图表设置','Chart style':'图表类型','Candles':'K 线','Bars':'美国线','Line':'线图','Area':'面积图','Baseline':'基线图','Heikin Ashi':'平均 K 线',
  'Undo':'撤销','Redo':'重做','Data window':'数据窗口','Object tree':'对象列表','Cursor':'光标','Crosshair':'十字线','Dot':'圆点','Arrow':'箭头','Eraser':'橡皮擦',
  'Lines':'线条','Lines — more':'更多线条','Trend line':'趋势线','Trend Line':'趋势线','Ray':'射线','Horizontal line':'水平线','Horizontal Line':'水平线','Horizontal ray':'水平射线',
  'Vertical line':'垂直线','Vertical Line':'垂直线','Extended line':'延长线','Parallel channel':'平行通道','Parallel Channel':'平行通道',
  'Fibonacci':'斐波那契','Fib retracement':'斐波那契回撤','Fib Retracement':'斐波那契回撤','Measurements':'测量','Date and price range':'日期与价格范围','Date Range':'日期范围','Price Range':'价格范围',
  'Shapes':'形状','Shapes — more':'更多形状','Rectangle':'矩形','Brush':'画笔','Freehand':'自由画笔','Text':'文字','Measure':'测量',
  'Eraser (click/drag to delete)':'橡皮擦（点击或拖动移除）','Magnet snap':'磁吸','Magnet snap — more':'磁吸强度','Off':'关闭','Weak':'弱','Strong':'强',
  'Stay in drawing mode':'保持绘图模式','Collapse toolbar':'收起工具栏','Expand toolbar':'展开工具栏',
  'Hide indicator legend':'隐藏指标图例','Show indicator legend':'显示指标图例','Volume':'成交量','Market Open':'市场开市','Market Closed':'市场休市',
  'Symbol':'品种','Status line':'状态栏','Scales and lines':'坐标轴与线条','Canvas':'画布','Advanced':'高级','Chart type':'图表类型','Type':'类型',
  'Body':'实体','Borders':'边框','Wick':'影线','Spacing':'间距','Animation':'动画','Animate zoom':'缩放动画','Pan momentum':'平移惯性','Animate price scale':'价格轴动画','Animate price changes':'价格变化动画',
  'Reveal on load':'加载动画','Time zone':'时区','Watermark':'水印','Symbol watermark':'品种水印','Reset defaults':'恢复默认','(UTC+8) Shanghai':'(UTC+8) 上海',
  'Inputs':'输入参数','Style':'样式','Properties':'属性','Visibility':'可见性','Settings':'设置','Source':'数据源','Length':'周期','Color':'颜色','Width':'宽度','Line style':'线型','Solid':'实线','Dashed':'虚线','Dotted':'点线',
  'DI length':'DI 周期','ADX smoothing':'ADX 平滑周期',
  'Reference lines':'参考线','Show upper level':'显示上方参考线','Upper level':'上方数值','Show lower level':'显示下方参考线','Lower level':'下方数值',
  'Save':'保存','Cancel':'取消','Apply':'应用','Ok':'确定','Close':'关闭','Hide':'隐藏','Show':'显示','Lock':'锁定','Unlock':'解锁','Clone':'复制','Duplicate':'复制','Remove':'移除','Remove all':'全部移除','Rename':'重命名',
  'Drawings':'绘图','Indicators':'指标','No drawings':'暂无绘图','No objects':'暂无对象','Search':'搜索','Search objects':'搜索对象','Bring to front':'置于顶层','Send to back':'置于底层',
  'Show all drawings':'显示所有绘图','Hide all drawings':'隐藏所有绘图','Lock all drawings':'锁定所有绘图','Unlock all drawings':'解锁所有绘图','Remove drawings':'移除绘图',
  'Coordinates':'坐标','Text color':'文字颜色','Font size':'字号','Background':'背景','Background color':'背景颜色','Grid':'网格','Vertical grid lines':'垂直网格线','Horizontal grid lines':'水平网格线',
  'Price scale':'价格轴','Time scale':'时间轴','Logarithmic':'对数','Regular':'线性','Auto':'自动','Invert scale':'反转坐标轴','Reset chart':'重置图表',
  'Move to':'移动到','New pane below':'新建下方副图','New pane above':'新建上方副图','Main pane':'主图','Merge up':'向上合并','Merge down':'向下合并',
  '1D':'1 天','7D':'7 天','1M':'1 月','3M':'3 月','6M':'6 月','YTD':'今年','1Y':'1 年','5Y':'5 年','ALL':'全部',
  'Glide the chart to each zoom step instead of jumping.':'平滑过渡到新的缩放比例。',
  'Keep gliding briefly after a drag release, and ease scroll-to-latest and keyboard pans.':'松开拖动后短暂延续平移，键盘平移也采用平滑过渡。',
  'Glide the price scale to its new range while zooming or panning.':'缩放和平移时平滑调整价格范围。',
  'Glide the live bar to each new price instead of snapping.':'实时价格更新时平滑过渡。',
  'Draw the candles in when a chart first loads. Takes effect on the next load.':'首次加载时逐步显示 K 线，下次加载生效。',
  'Interactive price chart. Use Left/Right arrows to move between bars, Shift+Arrow to pan, plus/minus to zoom, Home/End to jump, 0 to reset.':'价格图表。左右键移动十字线，Shift 加方向键平移，加减键缩放，Home/End 跳转，0 重置。',
}
const entries=Object.entries(vocabulary),keys=new Map(entries.map(([en,zh],i)=>[en,{key:'v'+i,en,zh}]))
i18n.global.mergeLocaleMessage('zh-CN',{chartNative:Object.fromEntries(entries.map(([,zh],i)=>['v'+i,zh]))})
i18n.global.mergeLocaleMessage('en',{chartNative:Object.fromEntries(entries.map(([en],i)=>['v'+i,en]))})
export function localizeChart(host:HTMLElement, symbols: () => ChartSymbol[] = () => []){
  // Retain each original string so ambiguous translations such as Close/closed
  // never change an English label when the user switches back to English.
  const originals = new WeakMap<Node, Map<string, { source: string; rendered: string }>>()
  const translate=(value:string):string=>{
    if (value === 'PTS') return cw('points')
    const replayLabel=value.replace(/\bREPLAY\d+\b/g,cw('replay'))
    if(replayLabel!==value)return replayLabel
    if (/^REPLAY\d*$/.test(value)) return cw('replay')
    const id = value.replace(/^(?:opentrading|heimdall|replay\d*):/, '')
    const symbol = symbols().find(item => item.id === id)
    if (symbol) return `${symbolName(symbol)} · ${workspaceMarketLabel(symbol.id)}`
    const named = symbols().find(item => item.metadata?.name_zh && [item.name, item.metadata.name_en, item.metadata.name_zh].includes(value))
    if (named) return symbolName(named)
    const key=keys.get(value)
    if(key)return i18n.global.t('chartNative.'+key.key)
    if(value.startsWith('Chart style — '))return i18n.global.t('chartNative.'+keys.get('Chart style')!.key)+' — '+translate(value.slice(14))
    if (i18n.global.locale.value !== 'en') {
      const period = value.match(/^(\d+) (minute|hour|day|week|month)s?$/)
      if (period) return period[1] + ({ minute: ' 分钟', hour: ' 小时', day: ' 天', week: ' 周', month: ' 月' }[period[2]] ?? '')
      const zone = value.match(/^(\(UTC[^)]*\)) (.+)$/)
      if (zone && keys.has(zone[2])) return `${zone[1]} ${translate(zone[2])}`
      if (value.startsWith('Move to ')) return '移动到 ' + translate(value.slice(8))
    }
    return messageText(value)
  }
  const update = (node: Node, field: string, value: string, write: (value: string) => void) => {
    let fields = originals.get(node)
    if (!fields) originals.set(node, fields = new Map())
    const saved = fields.get(field)
    const source = saved?.rendered === value ? saved.source : value
    const trimmed = source.trim()
    const sourceOption = field === 'text' && node.parentElement?.closest('option,.vela-select-trigger,.vela-select-item')
      && node.parentElement.closest('.vela-dialog--form,.vela-select-list')
    const translated = i18n.global.locale.value !== 'en' && trimmed === 'Close' &&
      (sourceOption || node.parentElement?.matches('.vela-dw-label')) ? sourceOption ? '收盘价' : '收盘' : translate(trimmed)
    const rendered = translated === trimmed ? source : source.replace(trimmed, translated)
    fields.set(field, { source, rendered })
    if (rendered !== value) write(rendered)
  }
  const scan=(root:Node)=>{
    if(root.nodeType===Node.TEXT_NODE){
      update(root, 'text', root.textContent ?? '', value => { root.textContent = value })
      return
    }
    if(!(root instanceof Element))return
    if(root.matches('script,style,textarea,.monaco-editor,[contenteditable="true"]'))return
    if(root.getAttribute('aria-label')==='Sync drawings on all charts')root.classList.add('cw-no-drawing-sync')
    for(const attr of ['aria-label','title','placeholder']){const value=root.getAttribute(attr);if(value)update(root,attr,value,next=>root.setAttribute(attr,next))}
    for(const node of root.childNodes)scan(node)
  }
  const observer=new MutationObserver(records=>{
    observer.disconnect()
    for(const r of records){if(r.type==='childList')for(const node of r.addedNodes)scan(node);else scan(r.target)}
    observe()
  })
  const observe=()=>observer.observe(host,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:['aria-label','title','placeholder']})
  scan(host);observe()
  const unwatch=watch(i18n.global.locale,()=>{observer.disconnect();scan(host);observe()})
  return ()=>{observer.disconnect();unwatch()}
}
