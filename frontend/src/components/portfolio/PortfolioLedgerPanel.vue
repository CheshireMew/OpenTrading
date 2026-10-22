<template>
  <section class="app-panel">
    <div class="app-panel-header flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
      <div>
        <h2 class="app-section-title">{{ t('portfolioLedger.title') }}</h2>
      </div>
      <div class="flex flex-wrap gap-2">
        <button type="button" class="app-button-secondary" @click="download('csv')">{{ t('portfolioLedger.exportCsv') }}</button>
        <button type="button" class="app-button-secondary" @click="download('json')">{{ t('portfolioLedger.exportJson') }}</button>
        <label class="app-button-secondary cursor-pointer">
          {{ t('portfolioLedger.import') }}
          <input type="file" class="sr-only" accept=".csv,.json,text/csv,application/json" @change="importFile" />
        </label>
        <button type="button" class="app-button-primary" @click="beginCreate">{{ t('portfolioLedger.addTransaction') }}</button>
      </div>
    </div>

    <div v-if="error" role="alert" class="m-5 flex flex-wrap items-center justify-between gap-3 border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-900/60 dark:bg-rose-950/30 dark:text-rose-200"><span>{{ error }}</span><button type="button" class="app-button-secondary app-touch-target" :disabled="loading" @click="load">{{ t('common.retry') }}</button></div>
    <div v-if="loading" class="p-8 text-center text-sm app-muted">{{ t('portfolioLedger.loading') }}</div>

    <template v-else-if="ledger">
      <div class="grid gap-px border-b bg-stone-200 dark:bg-slate-700 sm:grid-cols-2 xl:grid-cols-4" style="border-color:var(--app-border)">
        <div class="bg-white p-5 dark:bg-slate-800"><p class="text-xs app-muted">{{ t('portfolioLedger.totalEquity') }}</p><p class="mt-2 text-xl font-semibold text-stone-950 dark:text-white">{{ formatMoney(ledger.summary.totalEquity) }}</p></div>
        <div class="bg-white p-5 dark:bg-slate-800"><p class="text-xs app-muted">{{ t('portfolioLedger.totalPnl') }}</p><p class="mt-2 text-xl font-semibold" :class="tone(ledger.summary.totalPnl)">{{ formatSignedMoney(ledger.summary.totalPnl) }}</p></div>
        <div class="bg-white p-5 dark:bg-slate-800"><p class="text-xs app-muted">{{ t('portfolioLedger.netContributions') }}</p><p class="mt-2 text-xl font-semibold text-stone-950 dark:text-white">{{ formatMoney(ledger.summary.netContributions) }}</p></div>
        <div class="bg-white p-5 dark:bg-slate-800"><p class="text-xs app-muted">{{ t('portfolioLedger.return') }}</p><p class="mt-2 text-xl font-semibold" :class="tone(ledger.summary.simpleReturnPct)">{{ formatPercent(ledger.summary.simpleReturnPct) }}</p></div>
      </div>

      <div v-if="ledger.summary.issues?.length" class="m-5 border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800 dark:border-amber-800 dark:bg-amber-950/30 dark:text-amber-200">
        <p class="font-semibold">{{ t('portfolioLedger.incomplete') }}</p>
        <ul class="mt-2 list-disc space-y-1 pl-5"><li v-for="issue in (ledger.summary.issues || [])" :key="issue">{{ issue }}</li></ul>
      </div>

      <form v-if="showForm" class="m-5 space-y-4 border p-4 dark:border-slate-700" style="border-color:var(--app-border)" @submit.prevent="saveTransaction">
        <div class="flex items-center justify-between gap-4"><h3 class="font-semibold text-stone-950 dark:text-white">{{ editing ? t('portfolioLedger.editTransaction') : t('portfolioLedger.newTransaction') }}</h3><button type="button" class="text-sm app-muted underline" @click="cancelForm">{{ t('portfolioLedger.cancel') }}</button></div>
        <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <label class="space-y-1"><span class="label">{{ t('portfolioLedger.type') }}</span><select v-model="form.transactionType" class="app-control w-full"><option v-for="type in transactionTypes" :key="type" :value="type">{{ t(`portfolioLedger.types.${type}`) }}</option></select></label>
          <label v-if="isAssetTransaction" class="space-y-1"><span class="label">{{ t('portfolioLedger.symbol') }}</span><input v-model.trim="form.symbol" class="app-control w-full" placeholder="BTC" /></label>
          <label v-if="isAssetTransaction" class="space-y-1"><span class="label">{{ t('portfolioLedger.quantity') }}</span><input v-model.number="form.quantity" type="number" min="0" step="any" class="app-control w-full" /></label>
          <label v-if="isTrade" class="space-y-1"><span class="label">{{ t('portfolioLedger.unitPrice') }}</span><input v-model.number="form.unitPrice" type="number" min="0" step="any" class="app-control w-full" /></label>
          <label v-if="!isAssetTransaction" class="space-y-1"><span class="label">{{ t('portfolioLedger.cashAmount') }}</span><input v-model.number="form.cashAmount" type="number" min="0" step="any" class="app-control w-full" /></label>
          <label class="space-y-1"><span class="label">{{ t('portfolioLedger.fee') }}</span><input v-model.number="form.fee" type="number" min="0" step="any" class="app-control w-full" /></label>
          <label class="space-y-1"><span class="label">{{ t('portfolioLedger.currency') }}</span><input v-model.trim="form.currency" class="app-control w-full" maxlength="16" /></label>
          <label class="space-y-1"><span class="label">{{ t('portfolioLedger.occurredAt') }}</span><input v-model="form.occurredAt" type="datetime-local" class="app-control w-full" /></label>
          <label class="space-y-1"><span class="label">{{ t('portfolioLedger.externalId') }}</span><input v-model.trim="form.externalId" class="app-control w-full" maxlength="200" /></label>
        </div>
        <textarea v-model.trim="form.note" class="app-control min-h-20 w-full" :placeholder="t('portfolioLedger.note')" maxlength="10000" />
        <button type="submit" class="app-button-primary" :disabled="saving">{{ saving ? t('portfolioLedger.saving') : t('portfolioLedger.save') }}</button>
      </form>

      <div class="grid gap-5 p-5 2xl:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)]">
        <div class="min-w-0">
          <h3 class="font-semibold text-stone-950 dark:text-white">{{ t('portfolioLedger.derivedPositions') }}</h3>
          <div class="app-table-scroll mt-3 border dark:border-slate-700" style="border-color:var(--app-border)">
            <table class="min-w-full text-sm"><thead class="app-table-head"><tr><th class="px-3 py-2 text-left">{{ t('portfolioLedger.symbol') }}</th><th class="px-3 py-2 text-right">{{ t('portfolioLedger.units') }}</th><th class="px-3 py-2 text-right">{{ t('portfolioLedger.averageCost') }}</th><th class="px-3 py-2 text-right">{{ t('portfolioLedger.marketValue') }}</th><th class="px-3 py-2 text-right">{{ t('portfolioLedger.unrealized') }}</th></tr></thead><tbody><tr v-for="position in (ledger.summary.positions || [])" :key="position.symbol" class="app-table-row"><td class="px-3 py-3 font-semibold">{{ position.symbol }}</td><td class="px-3 py-3 text-right">{{ formatNumber(position.units) }}</td><td class="px-3 py-3 text-right">{{ formatMoney(position.averageCost) }}</td><td class="px-3 py-3 text-right">{{ formatMoney(position.marketValue) }}</td><td class="px-3 py-3 text-right" :class="tone(position.unrealizedPnl)">{{ formatSignedMoney(position.unrealizedPnl) }}</td></tr><tr v-if="!ledger.summary.positions?.length"><td colspan="5" class="px-4 py-8 text-center app-muted">{{ t('portfolioLedger.noPositions') }}</td></tr></tbody></table>
          </div>
        </div>

        <div class="min-w-0">
          <div class="flex items-center justify-between gap-3"><h3 class="font-semibold text-stone-950 dark:text-white">{{ t('portfolioLedger.transactions') }}</h3><select v-model="importMode" class="app-control"><option value="append">{{ t('portfolioLedger.importAppend') }}</option><option value="replace">{{ t('portfolioLedger.importReplace') }}</option></select></div>
          <div class="app-table-scroll mt-3 border dark:border-slate-700" style="border-color:var(--app-border)">
            <table class="min-w-[760px] w-full text-sm"><thead class="app-table-head"><tr><th class="px-3 py-2 text-left">{{ t('portfolioLedger.occurredAt') }}</th><th class="px-3 py-2 text-left">{{ t('portfolioLedger.type') }}</th><th class="px-3 py-2 text-left">{{ t('portfolioLedger.symbol') }}</th><th class="px-3 py-2 text-right">{{ t('portfolioLedger.quantity') }}</th><th class="px-3 py-2 text-right">{{ t('portfolioLedger.amount') }}</th><th class="px-3 py-2 text-right">{{ t('portfolioLedger.actions') }}</th></tr></thead><tbody><tr v-for="transaction in (ledger.transactions || [])" :key="transaction.id" class="app-table-row"><td class="px-3 py-3">{{ formatDateTime(transaction.occurredAt) }}</td><td class="px-3 py-3">{{ t(`portfolioLedger.types.${transaction.transactionType}`) }}</td><td class="px-3 py-3 font-semibold">{{ transaction.symbol || transaction.currency }}</td><td class="px-3 py-3 text-right">{{ transaction.quantity ? formatNumber(transaction.quantity) : '--' }}</td><td class="px-3 py-3 text-right">{{ formatMoney(transaction.cashAmount || transaction.quantity * transaction.unitPrice, transaction.currency) }}</td><td class="px-3 py-3 text-right"><button type="button" class="mr-3 text-emerald-700 underline dark:text-emerald-300" @click="beginEdit(transaction)">{{ t('portfolioLedger.edit') }}</button><button type="button" class="text-rose-600 underline dark:text-rose-300" @click="setArchived(transaction, true)">{{ t('portfolioLedger.archive') }}</button></td></tr><tr v-if="!ledger.transactions?.length"><td colspan="6" class="px-4 py-8 text-center app-muted">{{ t('portfolioLedger.noTransactions') }}</td></tr></tbody></table>
          </div>
          <details v-if="ledger.archivedTransactions?.length" class="mt-4"><summary class="cursor-pointer text-sm font-semibold app-muted">{{ t('portfolioLedger.archivedTransactions', { count: ledger.archivedTransactions?.length || 0 }) }}</summary><div class="mt-3 space-y-2"><div v-for="transaction in (ledger.archivedTransactions || [])" :key="transaction.id" class="flex items-center justify-between border p-3 text-sm dark:border-slate-700"><span>{{ formatDateTime(transaction.occurredAt) }} · {{ t(`portfolioLedger.types.${transaction.transactionType}`) }} · {{ transaction.symbol || transaction.currency }}</span><button type="button" class="text-emerald-700 underline dark:text-emerald-300" @click="setArchived(transaction, false)">{{ t('portfolioLedger.restore') }}</button></div></div></details>
        </div>
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { apiErrorMessage } from '@/api/request'
import { useDateTime } from '@/composables/useDateTime'
import { useMoney } from '@/composables/useMoney'
import { toolsApi } from '@/modules/tools'
import { parsePortfolioLedgerFile, portfolioLedgerCsv, portfolioLedgerJson } from '@/modules/tools/portfolioBalance/ledgerFiles'
import type { PortfolioLedgerResponse, PortfolioTransactionResponse } from '@/modules/tools/contracts'

const props = defineProps<{ portfolioId: string; priceRefreshKey?: string | null }>()
const emit = defineEmits<{ 'ledger-updated': [ledger: PortfolioLedgerResponse] }>()
const { t } = useI18n()
const { formatDateTime } = useDateTime()
const { formatMoney, formatSignedMoney } = useMoney()
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const ledger = ref<PortfolioLedgerResponse | null>(null)
const showForm = ref(false)
const editing = ref<PortfolioTransactionResponse | null>(null)
const importMode = ref<'append' | 'replace'>('append')
const transactionTypes = ['buy', 'sell', 'deposit', 'withdrawal', 'fee', 'transfer_in', 'transfer_out'] as const
const emptyForm = () => ({ transactionType: 'buy' as typeof transactionTypes[number], symbol: '', quantity: 0, unitPrice: 0, cashAmount: 0, fee: 0, currency: 'USD', externalId: '', note: '', occurredAt: new Date().toISOString().slice(0, 16) })
const form = reactive(emptyForm())
const isAssetTransaction = computed(() => ['buy', 'sell', 'transfer_in', 'transfer_out'].includes(form.transactionType))
const isTrade = computed(() => ['buy', 'sell'].includes(form.transactionType))

const load = async () => {
  if (!props.portfolioId) return
  loading.value = true
  error.value = ''
  ledger.value = null
  try {
    ledger.value = await toolsApi.getPortfolioLedger(props.portfolioId)
    emit('ledger-updated', ledger.value)
  }
  catch (cause) { error.value = apiErrorMessage(cause, t('portfolioLedger.loadFailed')) }
  finally { loading.value = false }
}

const beginCreate = () => { editing.value = null; Object.assign(form, emptyForm()); showForm.value = true }
const beginEdit = (row: PortfolioTransactionResponse) => {
  editing.value = row
  Object.assign(form, {
    transactionType: row.transactionType,
    symbol: row.symbol,
    quantity: row.quantity,
    unitPrice: row.unitPrice,
    cashAmount: row.cashAmount,
    fee: row.fee,
    currency: row.currency,
    externalId: row.externalId || '',
    note: row.note,
    occurredAt: new Date(row.occurredAt).toISOString().slice(0, 16),
  })
  showForm.value = true
}
const cancelForm = () => { showForm.value = false; editing.value = null }

const saveTransaction = async () => {
  saving.value = true
  error.value = ''
  const command = {
    transactionType: form.transactionType,
    symbol: form.symbol,
    quantity: Number(form.quantity || 0),
    unitPrice: Number(form.unitPrice || 0),
    cashAmount: Number(form.cashAmount || 0),
    fee: Number(form.fee || 0),
    currency: form.currency,
    feeCurrency: form.currency,
    externalId: form.externalId || null,
    note: form.note,
    metadata: {},
    occurredAt: new Date(form.occurredAt).toISOString(),
  }
  try {
    if (editing.value) await toolsApi.updatePortfolioTransaction(props.portfolioId, editing.value.id, { ...command, expectedVersion: editing.value.version })
    else await toolsApi.createPortfolioTransaction(props.portfolioId, command)
    cancelForm()
    await load()
  } catch (cause) { error.value = apiErrorMessage(cause, t('portfolioLedger.saveFailed')) }
  finally { saving.value = false }
}

const setArchived = async (row: PortfolioTransactionResponse, archived: boolean) => {
  try {
    await toolsApi.setPortfolioTransactionArchived(props.portfolioId, row.id, { expectedVersion: row.version }, archived)
    await load()
  } catch (cause) { error.value = apiErrorMessage(cause, t('portfolioLedger.saveFailed')) }
}

const importFile = async (event: Event) => {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  saving.value = true
  try {
    const transactions = await parsePortfolioLedgerFile(file)
    const response = await toolsApi.importPortfolioTransactions(props.portfolioId, { mode: importMode.value, transactions })
    ledger.value = response.ledger
    emit('ledger-updated', ledger.value)
  } catch (cause) { error.value = apiErrorMessage(cause, t('portfolioLedger.importFailed')) }
  finally { saving.value = false }
}

const download = (format: 'csv' | 'json') => {
  if (!ledger.value) return
  const rows = ledger.value.transactions || []
  const content = format === 'csv' ? portfolioLedgerCsv(rows) : portfolioLedgerJson(rows)
  const blob = new Blob([content], { type: format === 'csv' ? 'text/csv;charset=utf-8' : 'application/json;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `opentrading-ledger-${props.portfolioId}.${format}`
  anchor.click()
  URL.revokeObjectURL(url)
}

const tone = (value: number | null | undefined) => Number(value || 0) >= 0 ? 'text-emerald-600 dark:text-emerald-300' : 'text-rose-600 dark:text-rose-300'
const formatPercent = (value: number | null | undefined) => value == null ? '--' : `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`
const formatNumber = (value: number) => new Intl.NumberFormat(undefined, { maximumFractionDigits: 8 }).format(value)

watch(() => [props.portfolioId, props.priceRefreshKey], load, { immediate: true })
</script>
