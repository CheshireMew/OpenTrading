import { computed, ref, watch, onScopeDispose } from 'vue'
import { apiErrorMessage } from '@/api/request'
import { researchApi } from './api'
import type {
  ResearchAlertCreateCommand,
  ResearchAlertResponse,
  ResearchNoteCreateCommand,
  ResearchNoteResponse,
  ResearchWatchItemCreateCommand,
  ResearchWatchItemResponse,
  ResearchWatchlistResponse,
  ResearchWorkbenchResponse,
} from './contracts'

const replaceById = <T extends { id: string }>(rows: T[], value: T): T[] => {
  const index = rows.findIndex((row) => row.id === value.id)
  if (index < 0) return [...rows, value]
  return rows.map((row) => row.id === value.id ? value : row)
}

export const useResearchWorkbench = () => {
  const workbench = ref<ResearchWorkbenchResponse>({
    watchlists: [],
    items: [],
    notes: [],
    alerts: [],
    events: [],
    unacknowledgedEventCount: 0,
  })
  const loading = ref(false)
  const initialized = ref(false)
  const saving = ref(false)
  const error = ref('')
  const activeWatchlistId = ref('')
  const activeItemId = ref('')
  const notesLoading = ref(false), notesTotal = ref(0), notesOffset = ref(0)
  let notesGeneration = 0

  const watchlists = computed(() => workbench.value.watchlists || [])
  const activeWatchlists = computed(() => watchlists.value.filter((item) => !item.archivedAt))
  const archivedWatchlists = computed(() => watchlists.value.filter((item) => Boolean(item.archivedAt)))
  const items = computed(() => workbench.value.items || [])
  const activeWatchlist = computed(() => watchlists.value.find((item) => item.id === activeWatchlistId.value) || null)
  const activeItems = computed(() => items.value.filter((item) => item.watchlistId === activeWatchlistId.value && !item.archivedAt))
  const archivedItems = computed(() => items.value.filter((item) => item.watchlistId === activeWatchlistId.value && Boolean(item.archivedAt)))
  const activeItem = computed(() => items.value.find((item) => item.id === activeItemId.value) || null)
  const itemNotes = computed(() => (workbench.value.notes || []).filter((note) => (
    (!note.archivedAt && activeItem.value && (note.watchItemId === activeItem.value.id || note.symbol === activeItem.value.symbol))
  )))
  const archivedNotes = computed(() => (workbench.value.notes || []).filter((note) => (
    Boolean(note.archivedAt) && activeItem.value && (note.watchItemId === activeItem.value.id || note.symbol === activeItem.value.symbol)
  )))
  const itemAlerts = computed(() => (workbench.value.alerts || []).filter((alert) => (
    (!alert.archivedAt && activeItem.value && (alert.watchItemId === activeItem.value.id || alert.symbol === activeItem.value.symbol))
  )))

  const loadNotes = async (reset = false) => {
    const symbol = activeItem.value?.symbol
    const generation = ++notesGeneration
    if (!symbol) { workbench.value.notes = []; notesTotal.value = notesOffset.value = 0; notesLoading.value = false; return }
    const offset = reset ? 0 : notesOffset.value
    notesLoading.value = true
    try {
      const page = await researchApi.listNotes(symbol, offset, 200)
      if (generation !== notesGeneration || activeItem.value?.symbol !== symbol) return
      const existing = workbench.value.notes || []
      workbench.value.notes = reset ? page.items : [...existing, ...page.items.filter(note => !existing.some(old => old.id === note.id))]
      notesTotal.value = page.total; notesOffset.value = page.offset + page.items.length
    } catch (cause) {
      if (generation === notesGeneration) error.value = apiErrorMessage(cause, '研究笔记加载失败')
    } finally { if (generation === notesGeneration) notesLoading.value = false }
  }
  watch(() => activeItem.value?.symbol, () => { void loadNotes(true) })
  onScopeDispose(() => { notesGeneration++ })

  const load = async () => {
    if (loading.value) return
    loading.value = true
    error.value = ''
    try {
      workbench.value = await researchApi.getWorkbench()
      if (!activeWatchlistId.value || !activeWatchlists.value.some((row) => row.id === activeWatchlistId.value)) {
        activeWatchlistId.value = activeWatchlists.value[0]?.id || ''
      }
      if (!activeItemId.value || !activeItems.value.some((row) => row.id === activeItemId.value)) {
        activeItemId.value = activeItems.value[0]?.id || ''
      }
      await loadNotes(true)
    } catch (cause) {
      error.value = apiErrorMessage(cause, '研究数据加载失败')
    } finally {
      loading.value = false
      initialized.value = true
    }
  }

  const runMutation = async <T>(action: () => Promise<T>): Promise<T | null> => {
    saving.value = true
    error.value = ''
    try {
      return await action()
    } catch (cause) {
      error.value = apiErrorMessage(cause, '研究数据保存失败')
      return null
    } finally {
      saving.value = false
    }
  }

  const createWatchlist = async (name: string, description = '') => {
    const result = await runMutation(() => researchApi.createWatchlist({ name, description }))
    if (!result) return null
    workbench.value.watchlists = replaceById(watchlists.value, result)
    activeWatchlistId.value = result.id
    await refreshTimeline()
    return result
  }

  const saveWatchlist = async (row: ResearchWatchlistResponse, name: string, description: string) => {
    const result = await runMutation(() => researchApi.updateWatchlist(row.id, {
      expectedVersion: row.version,
      name,
      description,
    }))
    if (result) workbench.value.watchlists = replaceById(watchlists.value, result)
    return result
  }

  const setWatchlistArchived = async (row: ResearchWatchlistResponse, archived: boolean) => {
    const result = await runMutation(() => researchApi.setWatchlistArchived(
      row.id,
      { expectedVersion: row.version },
      archived,
    ))
    if (!result) return null
    workbench.value.watchlists = replaceById(watchlists.value, result)
    if (archived && activeWatchlistId.value === row.id) {
      activeWatchlistId.value = activeWatchlists.value[0]?.id || ''
      activeItemId.value = activeItems.value[0]?.id || ''
    }
    await refreshTimeline()
    return result
  }

  const createItem = async (command: ResearchWatchItemCreateCommand) => {
    const result = await runMutation(() => researchApi.createItem(command))
    if (!result) return null
    workbench.value.items = replaceById(items.value, result)
    activeWatchlistId.value = result.watchlistId
    activeItemId.value = result.id
    await refreshTimeline()
    return result
  }

  const saveItem = async (row: ResearchWatchItemResponse, command: ResearchWatchItemCreateCommand) => {
    const result = await runMutation(() => researchApi.updateItem(row.id, {
      ...command,
      expectedVersion: row.version,
    }))
    if (result) workbench.value.items = replaceById(items.value, result)
    await refreshTimeline()
    return result
  }

  const setItemArchived = async (row: ResearchWatchItemResponse, archived: boolean) => {
    const result = await runMutation(() => researchApi.setItemArchived(
      row.id,
      { expectedVersion: row.version },
      archived,
    ))
    if (!result) return null
    workbench.value.items = replaceById(items.value, result)
    if (archived && activeItemId.value === row.id) activeItemId.value = activeItems.value[0]?.id || ''
    await refreshTimeline()
    return result
  }

  const createNote = async (command: ResearchNoteCreateCommand) => {
    const result = await runMutation(() => researchApi.createNote(command))
    if (!result) return null
    workbench.value.notes = replaceById(workbench.value.notes || [], result)
    await loadNotes(true)
    await refreshTimeline()
    return result
  }

  const setNoteArchived = async (row: ResearchNoteResponse, archived: boolean) => {
    const result = await runMutation(() => researchApi.setNoteArchived(
      row.id,
      { expectedVersion: row.version },
      archived,
    ))
    if (result) workbench.value.notes = replaceById(workbench.value.notes || [], result)
    if (result) await loadNotes(true)
    await refreshTimeline()
    return result
  }

  const createAlert = async (command: ResearchAlertCreateCommand) => {
    const result = await runMutation(() => researchApi.createAlert(command))
    if (!result) return null
    workbench.value.alerts = replaceById(workbench.value.alerts || [], result)
    await refreshTimeline()
    return result
  }

  const deleteWatchlist = async (row:ResearchWatchlistResponse) => {const result=await runMutation(()=>researchApi.deleteWatchlist(row.id,row.version));if(result)await load();return result}
  const deleteItem = async (row:ResearchWatchItemResponse) => {const result=await runMutation(()=>researchApi.deleteItem(row.id,row.version));if(result)await load();return result}
  const deleteNote = async (row:ResearchNoteResponse) => {const result=await runMutation(()=>researchApi.deleteNote(row.id,row.version));if(result)await load();return result}

  const deleteAlert = async (row: ResearchAlertResponse) => {
    const result = await runMutation(() => researchApi.deleteAlert(row.id, row.version))
    if (result) workbench.value.alerts = (workbench.value.alerts ?? []).filter(alert => alert.id !== row.id)
    return result
  }

  const acknowledgeEvent = async (id: string, acknowledged = true) => {
    const result = await runMutation(() => researchApi.acknowledgeEvent(id, { acknowledged }))
    if (!result) return
    workbench.value.events = replaceById(workbench.value.events || [], result)
    workbench.value.unacknowledgedEventCount = Math.max(
      0,
      (workbench.value.events || []).filter((event) => !event.acknowledgedAt).length,
    )
  }

  const refreshTimeline = async () => {
    const fresh = await researchApi.getWorkbench()
    workbench.value.events = fresh.events
    workbench.value.unacknowledgedEventCount = fresh.unacknowledgedEventCount
  }

  const requestDesktopPermission = async () => {
    if (!('Notification' in window)) return 'unsupported'
    const result = await Notification.requestPermission()
    if (result === 'granted') window.dispatchEvent(new Event('opentrading:notification-permission'))
    return result
  }

  const evaluateAlerts = async () => {
    const result = await runMutation(() => researchApi.evaluateAlerts())
    if (result) await load()
    return result
  }

  return {
    workbench,
    loading,
    initialLoading: computed(() => loading.value && !initialized.value),
    saving,
    error,
    activeWatchlistId,
    activeItemId,
    watchlists,
    activeWatchlists,
    archivedWatchlists,
    activeWatchlist,
    activeItems,
    archivedItems,
    activeItem,
    itemNotes,
    archivedNotes,
    itemAlerts,
    notesLoading,
    hasMoreNotes: computed(() => notesOffset.value < notesTotal.value),
    loadMoreNotes: () => loadNotes(),
    load,
    createWatchlist,
    saveWatchlist,
    setWatchlistArchived,
    createItem,
    saveItem,
    setItemArchived,
    createNote,
    setNoteArchived,
    createAlert,
    deleteAlert, deleteWatchlist, deleteItem, deleteNote,
    acknowledgeEvent,
    requestDesktopPermission,
    evaluateAlerts,
  }
}
