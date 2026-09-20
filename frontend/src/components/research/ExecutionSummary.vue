<template>
  <div class="execution-summary text-sm app-muted space-y-2">
    <p>信号：{{ config.timeframe || '未记录' }}；模拟成交：{{ executionFrame }}；利润保护更新周期：{{ protectionFrame }}。已记录的收盘保护在更新后的下一根生效。主回撤按 {{ config.timeframe || '原记录周期' }} 收盘权益计算。</p>
    <p v-if="config.execution_timeframe">细周期匹配 {{ summary.matched_intervals ?? (completed ? '未记录' : '待检查') }} 段，回退主周期 {{ summary.fallback_intervals ?? (completed ? '未记录' : '待检查') }} 段<span v-if="summary.coverage_pct != null">，覆盖 {{ Number(summary.coverage_pct).toFixed(2) }}%</span>。{{ gapPolicy === 'reject' ? '缺失或不匹配时停止。' : gapPolicy === 'coarse_fallback' ? '缺失或不匹配时允许回退，相关交易保留记录。' : '原记录未注明缺失或不匹配时的处理方式。' }}</p>
    <p v-if="completed && provenance?.status === 'insufficient'">原记录证据不足：{{ missingNames }}。可查看原结果，使用当前引擎重新计算时会另建对照版本。</p>
    <p v-if="config.execution_timeframe && summary.fallback_intervals">细周期回撤包含回退区间的主周期收盘采样。</p>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
const props = defineProps<{ config: Record<string, unknown>; summary: Record<string, any>; completed?: boolean }>()
const executionFrame = computed(() => 'execution_timeframe' in props.summary ? props.summary.execution_timeframe ?? '未记录' : props.config.execution_timeframe || props.config.timeframe || '未记录')
const protectionFrame = computed(() => 'protection_timeframe' in props.summary ? props.summary.protection_timeframe ?? '未记录' : (props.config.intrabar_profit_protection ? props.config.execution_timeframe : props.config.timeframe) || '未记录')
const gapPolicy = computed(() => 'execution_gap_policy' in props.summary ? props.summary.execution_gap_policy : props.config.execution_gap_policy)
const provenance = computed(() => props.summary.provenance as { status: string; missing: string[] } | undefined)
const names: Record<string, string> = { environment: '运行环境', source: '数据来源', data_hash: '主行情版本', strategy_hash: '策略版本', warmup_bars: '预热记录', execution_bundle: '完整执行依赖', execution_data_hash: '细行情版本', execution_alignment_hash: '细周期对齐记录' }
const missingNames = computed(() => provenance.value?.missing.map(k => names[k] || k).join('、'))
</script>
