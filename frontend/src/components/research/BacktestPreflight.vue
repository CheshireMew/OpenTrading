<template>
  <section class="preflight text-sm">
    <p><strong>本地数据预览</strong> · 实际预热 {{ value.warmup_bars }} 根</p>
    <p class="app-muted my-2">{{ value.warmup_explanation }}</p>
    <p>请求交易区间：{{ value.config.start }} 至 {{ value.config.end }}</p>
    <div v-for="item in [value.signal_data, value.execution_data].filter(Boolean)" :key="item!.timeframe" class="my-3">
      <p>{{ item!.timeframe }} 所需数据：{{ date(item!.required_start_ms) }} 至 {{ date(item!.required_end_ms) }}</p>
      <p>本地缓存边界：{{ date(item!.first_cached_ms) }} 至 {{ date(item!.last_cached_close_ms) }}</p>
      <p>所需 {{ item!.expected_bars.toLocaleString() }} 根，已有 {{ item!.cached_bars.toLocaleString() }} 根，待获取 {{ item!.missing_bars.toLocaleString() }} 根。</p>
    </div>
    <p>本地连续数据与预热共同覆盖：</p><p v-if="!value.comparable_intervals.length">暂无完整区间，运行时需要获取数据。</p>
    <p v-for="v in value.comparable_intervals.slice(0, 20)" :key="v.start_ms">{{ date(v.start_ms) }} 至 {{ date(v.end_ms) }}</p>
    <details v-if="value.comparable_intervals.length > 20"><summary>全部 {{ value.comparable_intervals.length }} 段区间</summary><pre>{{ JSON.stringify(value.comparable_intervals, null, 2) }}</pre></details>
    <details class="my-3"><summary>本次规则说明</summary><p v-for="line in value.rules_summary" :key="line">{{ line }}</p></details>
    <p v-for="line in value.warnings" :key="line" class="app-muted text-xs mt-2">{{ line }}</p>
  </section>
</template>
<script setup lang="ts">
import type { LocalBacktestPreview } from '@/modules/research/generatedContracts'
defineProps<{ value: LocalBacktestPreview }>()
const date = (v: number | null | undefined) => v == null ? '无缓存' : new Date(v).toISOString().replace('T', ' ').slice(0, 16) + ' UTC'
</script>
<style scoped>.preflight{border:1px solid #8884;border-radius:10px;padding:14px;overflow-wrap:anywhere}pre{white-space:pre-wrap;max-height:250px;overflow:auto}summary{cursor:pointer}</style>
