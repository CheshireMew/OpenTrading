<template><div class="flex h-full min-h-0 min-w-0 flex-col"><ChartNavigation :controller="navigation" /><div ref="chartContainer" class="trading-chart relative flex-1 min-h-0 min-w-0" @dblclick="reset" /></div></template>

<script setup lang="ts">
import { DARK_CHART_COLORS } from '@/theme/palette.mjs'
import { useI18n } from 'vue-i18n'
import {computed,ref} from 'vue'
import ChartNavigation from '@/components/ChartNavigation.vue'

import { useTradingViewChart, type TradingViewChartProps } from './useTradingViewChart'

const props = withDefaults(defineProps<Partial<TradingViewChartProps>>(), {
  data: () => [],
  volumeData: () => [],
  chartType: 'candlestick',
  autoResize: true,
  colors: () => ({ ...DARK_CHART_COLORS }),
  strategyMarkers: () => [],
})

const emit = defineEmits<{ 'load-more': [] }>()
const { t } = useI18n()
const { chartContainer, getChart, isVisible, isResizing, setVisibleLogicalRange } = useTradingViewChart(props, emit, t)
const range=ref('all'),selecting=ref(false),enabled=computed(()=>props.data.length>1)
function zoom(direction:number){const scale=getChart()?.timeScale(),visible=scale?.getVisibleLogicalRange();if(!scale||!visible)return;const center=(visible.from+visible.to)/2,width=Math.max(5,(visible.to-visible.from)*(direction>0?.65:1.5));setVisibleLogicalRange({from:center-width/2,to:center+width/2});range.value='custom'}
function reset(){getChart()?.timeScale().fitContent();range.value='all'}
function selectRange(value:string){if(value==='all'){reset();return}const data=props.data,last=data[data.length-1];if(!last)return;const index=data.findIndex(point=>Number(point.time)>=Number(last.time)-Number(value)*86400);setVisibleLogicalRange({from:Math.max(0,index),to:data.length-1});range.value=value}
const navigation={range,selecting,enabled,zoom,reset,selectRange}

defineExpose({
  get chart() { return getChart() },
  isVisible,
  isResizing,
  setVisibleLogicalRange,
})
</script>
