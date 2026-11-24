<template>
  <span class="symbol-avatar" :style="{ background: appearance.background, color: appearance.color }" aria-hidden="true">
    <component :is="appearance.icon" v-if="appearance.icon" :size="16" stroke="1.7" />
    <span v-else>{{ base.slice(0, 2) }}</span>
  </span>
</template>

<script setup lang="ts">
import { computed, type Component } from 'vue'
import IconCurrencyBitcoin from '@tabler/icons-vue/icons/IconCurrencyBitcoin'
import IconCurrencyEthereum from '@tabler/icons-vue/icons/IconCurrencyEthereum'
import IconCurrencySolana from '@tabler/icons-vue/icons/IconCurrencySolana'
import IconBrandBinance from '@tabler/icons-vue/icons/IconBrandBinance'
import IconCurrencyTether from '@tabler/icons-vue/icons/IconCurrencyTether'
import IconCurrencyLitecoin from '@tabler/icons-vue/icons/IconCurrencyLitecoin'
import IconCurrencyDogecoin from '@tabler/icons-vue/icons/IconCurrencyDogecoin'
import IconCurrencyRipple from '@tabler/icons-vue/icons/IconCurrencyRipple'
import type { ChartSymbol } from '@/modules/chartWorkspace/api'

const props = defineProps<{ symbol?: ChartSymbol; fallback: string }>()
const base = computed(() => String(props.symbol?.metadata?.basecurrency ?? props.symbol?.name.split('/')[0]
  ?? props.fallback.split(':').pop() ?? '').toUpperCase())
const assets: Record<string, { icon: Component; background: string; color: string }> = {
  BTC: { icon: IconCurrencyBitcoin, background: '#f7931a', color: '#fff' },
  ETH: { icon: IconCurrencyEthereum, background: '#627eea', color: '#fff' },
  SOL: { icon: IconCurrencySolana, background: '#171921', color: '#9ce9d4' },
  BNB: { icon: IconBrandBinance, background: '#f0b90b', color: '#181a20' },
  USDT: { icon: IconCurrencyTether, background: '#26a17b', color: '#fff' },
  LTC: { icon: IconCurrencyLitecoin, background: '#345d9d', color: '#fff' },
  DOGE: { icon: IconCurrencyDogecoin, background: '#ba9f33', color: '#fff' },
  XRP: { icon: IconCurrencyRipple, background: '#252a30', color: '#fff' },
}
const appearance = computed(() => assets[base.value] ?? { icon: null, background: 'var(--ui-elevated)', color: 'var(--ui-muted)' })
</script>

<style scoped>
.symbol-avatar { display: inline-flex; align-items: center; justify-content: center; flex: 0 0 20px; width: 20px; height: 20px; overflow: hidden; border-radius: 50%; font-size: 8px; font-weight: 650; line-height: 1; }
</style>
