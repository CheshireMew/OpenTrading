import { watch } from 'vue'
import i18n from '@/i18n'

// Vela 0.7.6 exposes English chrome but no locale option. Keep the translation
// boundary outside its renderer; scripts, prices and the attribution stay intact.
const vocabulary:Record<string,string>={
  'LINES':'线条','CHANNELS':'通道','Add to favorites':'加入收藏','Remove from favorites':'取消收藏','Main chart':'主图',
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
  'Save':'保存','Cancel':'取消','Apply':'应用','Close':'关闭','Hide':'隐藏','Show':'显示','Lock':'锁定','Unlock':'解锁','Clone':'复制','Duplicate':'复制','Remove':'移除','Remove all':'全部移除','Rename':'重命名',
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
const reverse=new Map(entries.map(([en,zh])=>[zh,en]))
i18n.global.mergeLocaleMessage('zh-CN',{chartNative:Object.fromEntries(entries.map(([,zh],i)=>['v'+i,zh]))})
i18n.global.mergeLocaleMessage('en',{chartNative:Object.fromEntries(entries.map(([en],i)=>['v'+i,en]))})
export function localizeChart(host:HTMLElement){
  const translate=(value:string):string=>{
    const key=keys.get(reverse.get(value)??value)
    if(key)return i18n.global.t('chartNative.'+key.key)
    if(value.startsWith('Chart style — '))return i18n.global.t('chartNative.'+keys.get('Chart style')!.key)+' — '+translate(value.slice(14))
    return value
  }
  const scan=(root:Node)=>{
    if(root.nodeType===Node.TEXT_NODE){
      const text=root.textContent??'',trimmed=text.trim(),translated=translate(trimmed)
      if(translated!==trimmed)root.textContent=text.replace(trimmed,translated)
      return
    }
    if(!(root instanceof Element))return
    if(root.matches('script,style,textarea,input,.monaco-editor'))return
    if(root.getAttribute('aria-label')==='Sync drawings on all charts')root.classList.add('cw-no-drawing-sync')
    for(const attr of ['aria-label','title','placeholder']){const value=root.getAttribute(attr);if(value&&translate(value)!==value)root.setAttribute(attr,translate(value))}
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
