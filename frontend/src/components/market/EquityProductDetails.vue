<template>
  <div class="eq-products" :class="`eq-products--${arrangement}`">
    <section v-for="group in groups" :key="group.id" class="eq-product-group" :aria-label="`${item.ticker} ${group.label}`">
      <header class="eq-product-group-heading">
        <h3>{{ group.label }}</h3>
        <span>{{ t('equities.productCount', { count: group.offerings.length }) }}</span>
      </header>
      <ul>
        <li v-for="offering in group.offerings" :key="`${offering.source_id}:${offering.symbol}`" class="eq-product">
          <span class="eq-product-kind">{{ t(`equities.${offering.trading_type}`) }}</span>
          <a :href="offering.url" target="_blank" rel="noopener noreferrer" :title="offering.product">
            {{ offering.symbol }}<ArrowUpRightIcon aria-hidden="true" />
          </a>
          <span class="eq-product-name">{{ offering.product }}</span>
          <span class="eq-product-quote">{{ offering.quote }}</span>
          <span v-if="restricted(offering.status) || stale(offering.source_id)" class="eq-product-warning">
            {{ restricted(offering.status) ? t('equities.restricted') : t('equities.cached') }}
          </span>
        </li>
      </ul>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { ArrowUpRightIcon } from '@heroicons/vue/24/outline'
import type { EquityCatalogItemResponse, EquityCatalogSourceResponse } from '@/modules/market/contracts'

const props = defineProps<{
  item: EquityCatalogItemResponse
  sources: EquityCatalogSourceResponse[]
  arrangement: 'stack' | 'columns' | 'rows'
}>()
const { t } = useI18n()
const groups = computed(() => ['binance', 'okx', 'bitget'].map(id => ({
  id,
  label: id === 'binance' ? t('equities.binance') : id === 'okx' ? 'OKX' : 'Bitget',
  offerings: props.item.offerings.filter(item => item.platform === id)
    .slice().sort((a, b) => a.trading_type.localeCompare(b.trading_type) * -1 || a.product.localeCompare(b.product)),
})).filter(group => group.offerings.length))
const restricted = (status: string) => !['trading', 'TRADING', 'BUY_SELL', 'live', 'online'].includes(status)
const stale = (id: string) => props.sources.find(source => source.id === id)?.status === 'stale'
</script>
