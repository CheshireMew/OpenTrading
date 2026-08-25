<template>
  <div class="relative">
    <button
      type="button"
      class="symbol-trigger"
      aria-haspopup="dialog"
      :aria-expanded="open"
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
          aria-labelledby="symbol-search-title"
          tabindex="-1"
          class="mx-auto flex max-h-[88vh] w-full max-w-5xl flex-col overflow-hidden border border-[#d8d1c5] bg-[#fbfaf7] shadow-2xl outline-none dark:border-gray-700 dark:bg-gray-900"
        >
          <div class="flex items-center justify-between border-b border-[#e4ded3] px-5 py-4 dark:border-gray-700">
            <h2 id="symbol-search-title" class="text-lg font-semibold text-stone-950 dark:text-white">{{ t('symbolSearch.title') }}</h2>
            <button type="button" :aria-label="t('common.close')" class="p-2 text-stone-500 transition hover:bg-[#f1ece3] dark:text-gray-300 dark:hover:bg-gray-800" @click="closeSearch">
              <XMarkIcon class="h-5 w-5" />
            </button>
          </div>

          <div class="border-b border-[#e4ded3] p-4 dark:border-gray-700">
            <div class="flex items-center border border-[#d8d1c5] bg-white px-3 dark:border-gray-600 dark:bg-gray-950">
              <MagnifyingGlassIcon class="h-5 w-5 shrink-0 text-stone-400" />
              <input
                ref="searchInput"
                v-model.trim="query"
                type="text"
                class="h-12 min-w-0 flex-1 bg-transparent px-3 text-base text-stone-950 outline-none dark:text-white"
                :placeholder="placeholderText"
                @keydown.enter.prevent="selectFirst"
              />
              <button
                v-if="query"
                type="button"
                class="p-1 text-stone-400 transition hover:bg-[#f1ece3] hover:text-stone-700 dark:hover:bg-gray-800"
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
                class="px-3 py-1.5 text-sm font-medium transition"
                :class="activeClass === tab.value ? 'bg-[#0f6b4f] text-white dark:bg-emerald-500 dark:text-gray-950' : 'border border-[#e4ded3] bg-white text-stone-700 hover:bg-[#f1ece3] dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200 dark:hover:bg-gray-700'"
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
              class="grid w-full grid-cols-[minmax(6rem,10rem)_minmax(0,1fr)_5rem_6rem] items-center gap-3 border-b border-[#eee8dd] px-5 py-3 text-left transition hover:bg-[#f6f1e8] dark:border-gray-800 dark:hover:bg-gray-800/70"
              :class="[
                isSelected(item) ? 'bg-[#edf3ee] dark:bg-emerald-950/30' : '',
                isDisabled(item) ? 'cursor-not-allowed opacity-45 hover:bg-transparent dark:hover:bg-transparent' : '',
              ]"
              @click="choose(item)"
            >
              <span class="font-semibold text-[#0f6b4f] dark:text-emerald-300">{{ item.symbol }}</span>
              <span class="min-w-0 truncate text-gray-900 dark:text-white">{{ item.name }}</span>
              <span class="text-sm text-gray-500 dark:text-gray-400">{{ marketLabel(item) }}</span>
              <span class="justify-self-end border border-[#e4ded3] bg-white px-2 py-1 text-xs font-medium text-stone-600 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300">
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
import { computed, nextTick, onMounted, ref } from 'vue'
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
const { symbols, loadSymbols } = useSymbolCatalog()
const open = ref(false)
const catalogLoading = ref(false)
const catalogError = ref('')
const query = ref('')
const searchInput = ref<HTMLInputElement | null>(null)
const activeClass = ref('all')
const { dialogRef } = useModalDialog(open, closeSearch)

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
  await nextTick()
  searchInput.value?.focus()
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
  @apply flex h-10 w-full items-center justify-between gap-2 border px-3 text-left text-sm outline-none transition dark:border-gray-600 dark:bg-gray-900;
  background: #fff;
  border-color: #e4ded3;
}

.symbol-trigger:hover,
.symbol-trigger:focus {
  border-color: #0f6b4f;
}
</style>
