import { nextTick, onActivated, onBeforeUnmount, onMounted, ref } from 'vue'
import * as echarts from 'echarts/core'
import { DataZoomComponent, ToolboxComponent } from 'echarts/components'

echarts.use([DataZoomComponent,ToolboxComponent])

export function useEcharts(buildOption: () => Record<string, unknown>) {
  const chartContainer = ref<HTMLElement | null>(null)
  let chartInstance: echarts.ECharts | null = null
  let resizeObserver: ResizeObserver | null = null
  let disposed=false, signature=''
  const range=ref('all'),selecting=ref(false),enabled=ref(false)
  let start=0,end=100
  const axes=()=>((chartInstance?.getOption() as any)?.xAxis??[]) as {data?:unknown[]}[]
  function applyRange(from:number,to:number){start=Math.max(0,from);end=Math.min(100,to);range.value='custom';chartInstance?.dispatchAction({type:'dataZoom',start,end})}
  function zoom(direction:number){const width=Math.max(2,Math.min(100,(end-start)*(direction>0?.65:1.5))),center=(start+end)/2,from=Math.max(0,Math.min(100-width,center-width/2));applyRange(from,from+width)}
  function reset(){start=0;end=100;range.value='all';selecting.value=false;chartInstance?.dispatchAction({type:'takeGlobalCursor',key:'dataZoomSelect',dataZoomSelectActive:false});chartInstance?.dispatchAction({type:'dataZoom',start:0,end:100});range.value='all'}
  function selectRange(value:string){
    if(value==='all'){reset();return}
    const data=axes()[0]?.data??[],last=Date.parse(String(data[data.length-1]??'')),days=Number(value)
    let index=data.findIndex(item=>Date.parse(String(item))>=last-days*86400000)
    if(!Number.isFinite(last)||index<0)index=Math.max(0,data.length-days)
    applyRange(data.length>1?index/(data.length-1)*100:0,100);range.value=value
  }
  function toggleSelect(){selecting.value=!selecting.value;chartInstance?.dispatchAction({type:'takeGlobalCursor',key:'dataZoomSelect',dataZoomSelectActive:selecting.value})}
  const navigation={range,selecting,enabled,zoom,reset,selectRange,toggleSelect}

  const renderChart = async () => {
    await nextTick()
    if (disposed||!chartContainer.value) return
    if (!chartInstance) {
      chartInstance = echarts.init(chartContainer.value)
      chartInstance.on('datazoom',()=>{const current=(chartInstance?.getOption() as any)?.dataZoom?.[0];if(current){start=current.start??0;end=current.end??100;range.value=start===0&&end===100?'all':'custom'}})
      chartInstance.getZr().on('dblclick',reset)
    }
    const option=buildOption() as any,xAxes=Array.isArray(option.xAxis)?option.xAxis:option.xAxis?[option.xAxis]:[]
    const data=xAxes[0]?.data??[],next=JSON.stringify([data.length,data[0],data[data.length-1]])
    enabled.value=data.length>1
    if(!xAxes.length){chartInstance.clear();return}
    if(next!==signature){start=0;end=100;range.value='all';selecting.value=false;signature=next}
    const indices=xAxes.map((_:unknown,index:number)=>index)
    const zooms=option.dataZoom??[{type:'inside',xAxisIndex:indices,zoomOnMouseWheel:'ctrl'}, {type:'slider',xAxisIndex:indices,bottom:0,height:14,showDetail:false}]
    option.dataZoom=zooms.map((zoom:Record<string,unknown>)=>({...zoom,start,end}))
    // ECharts only mounts its rectangle-selection handler when the toolbox is
    // rendered. Its icons live off-canvas; the accessible DOM toolbar controls it.
    option.toolbox={show:true,left:-1000,top:-1000,feature:{dataZoom:{xAxisIndex:indices,yAxisIndex:false}}}
    chartInstance.setOption(option,{replaceMerge:['series','dataZoom']})
  }

  const resizeChart = () => {
    chartInstance?.resize()
  }

  onMounted(() => {
    window.addEventListener('resize', resizeChart)
    resizeObserver = new ResizeObserver(resizeChart)
    if (chartContainer.value) resizeObserver.observe(chartContainer.value)
    renderChart()
  })

  onBeforeUnmount(() => {
    disposed=true
    window.removeEventListener('resize', resizeChart)
    resizeObserver?.disconnect()
    if (!chartInstance) return
    chartInstance.dispose()
    chartInstance = null
  })
  onActivated(resizeChart)

  return {
    chartContainer,
    renderChart,
    resizeChart,
    navigation,
  }
}
