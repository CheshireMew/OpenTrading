<template>
  <select
    :value="displayCurrency"
    class="app-control w-full px-3 py-2"
    @change="handleChange"
  >
    <option v-for="option in currencyOptions" :key="option.value" :value="option.value">
      {{ option.value }} · {{ currencyName(option.value) }}
    </option>
  </select>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useMoney } from '@/composables/useMoney'
import { useI18n } from 'vue-i18n'

const { displayCurrency, currencyOptions, setDisplayCurrency, loadCurrencyRates } = useMoney()
const { locale } = useI18n()
const currencyName = (code: string) => new Intl.DisplayNames(locale.value, { type: 'currency' }).of(code) ?? code

const handleChange = (event: Event) => {
  setDisplayCurrency((event.target as HTMLSelectElement).value)
}

onMounted(() => {
  loadCurrencyRates()
})
</script>
