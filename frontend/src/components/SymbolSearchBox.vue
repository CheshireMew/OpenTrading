<template>
  <div class="relative">
    <button
      type="button"
      class="symbol-trigger"
      aria-haspopup="dialog"
      :aria-expanded="open"
      :aria-controls="open ? dialogId : undefined"
      :aria-label="ariaLabel || placeholderText"
      :disabled="disabled"
      :class="[triggerClass, disabled ? 'cursor-not-allowed opacity-60' : '']"
      @click="openSearch"
    >
      <span class="truncate" :class="displayText ? 'text-gray-900 dark:text-white' : 'text-gray-400 dark:text-gray-500'">
        {{ displayText || placeholderText }}
      </span>
      <MagnifyingGlassIcon class="h-4 w-4 shrink-0 text-gray-400" />
    </button>

    <Teleport to="body">
      <div v-if="open" class="fixed inset-0 z-50 bg-black/30 p-3 backdrop-blur-sm sm:p-6" @click.self="closeSearch">
        <section
          ref="dialogRef"
          role="dialog"
          aria-modal="true"
          :id="dialogId"
          :aria-labelledby="titleId"
          tabindex="-1"
          class="symbol-dialog mx-auto flex w-full max-w-3xl flex-col overflow-hidden border shadow-xl outline-none"
        >
          <div class="flex items-center justify-between border-b border-[#e4ded3] px-5 py-4 dark:border-gray-700">
            <h2 :id="titleId" class="text-lg font-semibold text-stone-950 dark:text-white">{{ t('symbolSearch.title') }}</h2>
            <button type="button" :aria-label="t('common.close')" class="app-icon-button" @click="closeSearch">
              <XMarkIcon class="h-5 w-5" />
            </button>
          </div>

          <div class="border-b border-[#e4ded3] p-4 dark:border-gray-700">
            <div class="symbol-search-field flex items-center border px-3">
              <MagnifyingGlassIcon class="h-5 w-5 shrink-0 text-stone-400" />
              <input
                ref="searchInput"
                v-model.trim="query"
                type="search"
                class="h-12 min-w-0 flex-1 bg-transparent px-3 text-base text-stone-950 outline-none dark:text-white"
                :placeholder="placeholderText"
                :aria-label="placeholderText"
                @keydown.enter.prevent="selectFirst"
              />
              <button
                v-if="query"
                type="button"
                :aria-label="t('symbolSearch.clear')"
                class="app-icon-button"
                @click="query = ''"
              >
                <XMarkIcon class="h-4 w-4" />
              </button>
            </div>

            <div class="mt-4 flex flex-wrap gap-2">
              <button
                v-for="tab in visibleTabs"
                :key="tab.value"
                type="button"
                :aria-pressed="activeClass === tab.value"
                class="app-segment-button"
                :class="{ 'is-active': activeClass === tab.value }"
                @click="activeClass = tab.value"
              >
                {{ tab.label }}
              </button>
            </div>
          </div>

          <div class="min-h-0 flex-1 overflow-y-auto">
            <div v-if="catalogLoading" role="status" aria-live="polite" class="px-5 py-10 text-center text-sm text-gray-500 dark:text-gray-400">
              {{ t('symbolSearch.loading') }}
            </div>
            <div v-else-if="catalogError" role="alert" class="px-5 py-10 text-center text-sm text-rose-700 dark:text-rose-300">
              <p>{{ catalogError }}</p>
              <button type="button" class="app-button-secondary app-touch-target mt-4" @click="loadCatalog">{{ t('common.retry') }}</button>
            </div>
            <button
              v-else
              v-for="item in filteredSymbols"
              :key="item.symbol"
              type="button"
              :disabled="isDisabled(item)"
              :aria-pressed="isSelected(item)"
              class="symbol-result grid w-full items-center gap-x-3 gap-y-1 border-b px-5 py-3 text-left transition"
              :class="[
                isSelected(item) ? 'bg-[#edf3ee] dark:bg-emerald-950/30' : '',
                isDisabled(item) ? 'cursor-not-allowed opacity-45 hover:bg-transparent dark:hover:bg-transparent' : '',
              ]"
              @click="choose(item)"
            >
              <span class="symbol-result-symbol font-semibold">{{ item.symbol }}</span>
              <span class="symbol-result-name min-w-0 truncate text-gray-900 dark:text-white">{{ item.name !== item.symbol ? item.name : '' }}</span>
              <span class="symbol-result-market text-xs app-muted">{{ marketLabel(item) }}</span>
              <span class="symbol-result-kind app-chip justify-self-end">
                {{ isDisabled(item) ? disabledText : classLabel(item.asset_class) }}
              </span>
            </button>

            <div v-if="!catalogLoading && !catalogError && !filteredSymbols.length" class="px-5 py-10 text-center text-sm text-gray-500 dark:text-gray-400">
              {{ t('symbolSearch.noMatches') }}
            </div>
          </div>
        </section>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, useId } from 'vue'
import { useI18n } from 'vue-i18n'
import { MagnifyingGlassIcon, XMarkIcon } from '@heroicons/vue/24/outline'
import { useModalDialog } from '@/composables/useModalDialog'
import { toBaseSymbol, useSymbolCatalog } from '@/modules/market'
import type { MarketSymbolSearchItem } from '@/modules/market/contracts'

const props = withDefaults(defineProps<{
  modelValue: string | string[]
  multiple?: boolean
  allowedClasses?: string[]
  outputMode?: 'symbol' | 'base'
  placeholder?: string
  triggerClass?: string
  disabled?: boolean
  disabledLabel?: string
  ariaLabel?: string
}>(), {
  multiple: false,
  allowedClasses: () => ['crypto', 'index'],
  outputMode: 'symbol',
  placeholder: '',
  triggerClass: '',
  disabled: false,
  disabledLabel: '',
  ariaLabel: '',
})

const emit = defineEmits<{
  'update:modelValue': [value: string | string[]]
  select: [item: MarketSymbolSearchItem]
}>()

const { t } = useI18n()
const dialogId = useId()
const titleId = `${dialogId}-title`
const { symbols, loadSymbols } = useSymbolCatalog()
const open = ref(false)
const catalogLoading = ref(false)
const catalogError = ref('')
const query = ref('')
const searchInput = ref<HTMLInputElement | null>(null)
const activeClass = ref('all')
const { dialogRef } = useModalDialog(open, closeSearch, searchInput)

const placeholderText = computed(() => props.placeholder || t('symbolSearch.placeholder'))
const disabledText = computed(() => props.disabledLabel || t('symbolSearch.disabled'))
const tabs = computed(() => [
  { value: 'all', label: t('symbolSearch.tabs.all') },
  { value: 'crypto', label: t('symbolSearch.tabs.crypto') },
  { value: 'index', label: t('symbolSearch.tabs.index') },
  { value: 'cash', label: t('symbolSearch.tabs.cash') },
])

const visibleTabs = computed(() => tabs.value.filter((tab) => tab.value === 'all' || props.allowedClasses.includes(tab.value)))

const normalizedSelected = computed(() => {
  const value = props.modelValue
  return Array.isArray(value) ? value : String(value || '').split(',').map((item) => item.trim()).filter(Boolean)
})

const displayText = computed(() => {
  if (props.multiple) return normalizedSelected.value.join(', ')
  return String(props.modelValue || '')
})

const candidates = computed(() => symbols.value
  .map((item, index) => ({ item, index, allowed: props.allowedClasses.includes(item.asset_class) }))
  .sort((left, right) => Number(right.allowed) - Number(left.allowed) || left.index - right.index)
  .map(({ item }) => item))

const filteredSymbols = computed(() => {
  const needle = query.value.toUpperCase()
  return candidates.value
    .filter((item) => activeClass.value === 'all' || item.asset_class === activeClass.value)
    .filter((item) => {
      if (!needle) return true
      return `${item.symbol} ${item.name} ${item.market} ${item.exchange || ''} ${(item.aliases || []).join(' ')}`.toUpperCase().includes(needle)
    })
    .slice(0, 80)
})

const outputValue = (item: MarketSymbolSearchItem) => props.outputMode === 'base' ? toBaseSymbol(item.symbol) : item.symbol

const openSearch = async () => {
  if (props.disabled) return
  open.value = true
  await loadCatalog()
}

const loadCatalog = async () => {
  if (symbols.value.length) return
  catalogLoading.value = true
  catalogError.value = ''
  try {
    await loadSymbols()
  } catch {
    catalogError.value = t('symbolSearch.loadFailed')
  } finally {
    catalogLoading.value = false
  }
}

function closeSearch() {
  open.value = false
  query.value = ''
}

const choose = (item: MarketSymbolSearchItem) => {
  if (isDisabled(item)) return
  const value = outputValue(item)
  if (props.multiple) {
    const current = normalizedSelected.value
    emit('update:modelValue', current.includes(value)
      ? current.filter((item) => item !== value)
      : [...current, value])
  } else {
    emit('update:modelValue', value)
    closeSearch()
  }
  emit('select', item)
}

const selectFirst = () => {
  const first = filteredSymbols.value.find((item) => !isDisabled(item))
  if (first) choose(first)
}

const isSelected = (item: MarketSymbolSearchItem) => normalizedSelected.value.includes(outputValue(item))
const isDisabled = (item: MarketSymbolSearchItem) => !props.allowedClasses.includes(item.asset_class)
const classLabel = (value: string) => {
  if (value === 'crypto') return t('symbolSearch.tabs.crypto')
  if (value === 'index') return t('symbolSearch.tabs.index')
  if (value === 'cash') return t('symbolSearch.tabs.cash')
  return value
}
const marketLabel = (item: MarketSymbolSearchItem) => item.exchange || item.market

onMounted(() => {
  void loadCatalog()
})
</script>

<style scoped>
.symbol-trigger {
  @apply flex w-full items-center justify-between gap-2 border px-3 text-left text-sm transition;
  min-height: 38px;
  border-radius: 5px;
  background: var(--ui-toolbar);
  border-color: var(--ui-borderStrong);
}

.symbol-trigger:hover:not(:disabled),
.symbol-trigger:focus-visible {
  border-color: var(--ui-accent);
}
.symbol-dialog { max-height: min(88dvh, 720px); border-radius: 10px; border-color: var(--ui-borderStrong); background: var(--ui-panel); }
.symbol-dialog > div { border-color: var(--ui-border); }
.symbol-search-field { border-radius: 6px; border-color: var(--ui-borderStrong); background: var(--ui-toolbar); }
.symbol-search-field:focus-within { border-color: var(--ui-accent); outline: 2px solid var(--ui-accent); outline-offset: 2px; }
.symbol-search-field input:focus-visible { outline: none; }
.symbol-search-field input::-webkit-search-cancel-button { display: none; }
.symbol-result { grid-template-columns: minmax(0, 1fr) auto; border-color: var(--ui-border); }
.symbol-result:hover:not(:disabled) { background: var(--ui-elevated); }
.symbol-result-symbol { color: var(--ui-accent); overflow-wrap: anywhere; }
.symbol-result-name { grid-column: 1; grid-row: 2; font-size: 13px; }
.symbol-result-market { grid-column: 2; grid-row: 2; }
.symbol-result-kind { grid-column: 2; grid-row: 1; }
@media (min-width: 640px) {
  .symbol-result { grid-template-columns: minmax(7rem, 10rem) minmax(0, 1fr) 5rem 6rem; }
  .symbol-result-name, .symbol-result-market, .symbol-result-kind { grid-column: auto; grid-row: auto; }
}
@media (max-width: 767px), (pointer: coarse) { .symbol-trigger { min-height: 44px; } }
</style>
