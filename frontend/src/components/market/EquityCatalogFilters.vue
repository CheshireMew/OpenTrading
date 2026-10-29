<template>
  <div class="eq-filters" :class="`eq-filters--${variant}`">
    <fieldset class="eq-filter-platform">
      <legend :class="variant === 'bar' ? 'sr-only' : ''">{{ t('equities.platform') }}</legend>
      <select v-if="variant === 'bar'" v-model="platform" :aria-label="t('equities.platform')" class="eq-control">
        <option value="all">{{ t('equities.allPlatforms') }}</option>
        <option v-for="value in platforms" :key="value" :value="value">{{ platformName(value) }}</option>
      </select>
      <template v-else>
        <label v-for="value in ['all', ...platforms]" :key="value" class="eq-filter-choice">
          <input v-model="platform" type="radio" :name="`${id}-platform`" :value="value" />
          <span>{{ value === 'all' ? t('equities.allPlatforms') : platformName(value) }}</span>
        </label>
      </template>
    </fieldset>
    <fieldset class="eq-filter-kind">
      <legend :class="variant === 'bar' ? 'sr-only' : ''">{{ t('equities.assetType') }}</legend>
      <select v-if="variant === 'bar'" v-model="assetType" :aria-label="t('equities.assetType')" class="eq-control">
        <option v-for="option in assetOptions" :key="option.id" :value="option.id">{{ option.label }}</option>
      </select>
      <template v-else>
        <label v-for="option in assetOptions" :key="option.id" class="eq-filter-choice">
          <input v-model="assetType" type="radio" :name="`${id}-asset`" :value="option.id" />
          <span>{{ option.label }}</span>
        </label>
      </template>
    </fieldset>
    <fieldset class="eq-filter-trading" :class="{ 'eq-segmented': variant === 'bar' }">
      <legend :class="variant === 'bar' ? 'sr-only' : ''">{{ t('equities.tradingType') }}</legend>
      <label v-for="option in tradingOptions" :key="option.id" class="eq-filter-choice">
        <input v-model="tradingType" type="radio" :name="`${id}-trading`" :value="option.id" />
        <span>{{ option.label }}</span>
        <small v-if="option.count != null && variant === 'bar'">{{ option.count.toLocaleString() }}</small>
      </label>
    </fieldset>
    <label class="eq-filter-choice eq-filter-shared">
      <input v-model="sharedOnly" type="checkbox" />
      <span>{{ t('equities.sharedOnly') }}</span>
    </label>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const props = defineProps<{ id: string; variant: 'bar' | 'sidebar'; spotCount: number | null; perpetualCount: number | null }>()
const platform = defineModel<string>('platform', { required: true })
const assetType = defineModel<string>('assetType', { required: true })
const tradingType = defineModel<string>('tradingType', { required: true })
const sharedOnly = defineModel<boolean>('sharedOnly', { required: true })
const { t } = useI18n()
const platforms = ['binance', 'okx', 'bitget']
const platformName = (value: string) => value === 'binance' ? t('equities.binance') : value === 'okx' ? 'OKX' : 'Bitget'
const assetOptions = computed(() => [
  { id: 'all', label: t('equities.allAssets') },
  ...['stock', 'etf', 'index', 'unknown'].map(id => ({ id, label: t(`equities.${id}`) })),
])
const tradingOptions = computed(() => [
  { id: 'all', label: t('equities.allTradingShort'), count: null },
  { id: 'spot', label: t('equities.spot'), count: props.spotCount },
  { id: 'perpetual', label: t('equities.perpetual'), count: props.perpetualCount },
  { id: 'both', label: t('equities.bothShort'), count: null },
])
</script>
