import { computed, ref } from 'vue'
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
  const saving = ref(false)
  const error = ref('')
  const activeWatchlistId = ref('')
  const activeItemId = ref('')

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
  const archivedAlerts = computed(() => (workbench.value.alerts || []).filter((alert) => (
    Boolean(alert.archivedAt) && activeItem.value && (alert.watchItemId === activeItem.value.id || alert.symbol === activeItem.value.symbol)
  )))

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
    } catch (cause) {
      error.value = apiErrorMessage(cause, '研究数据加载失败')
    } finally {
      loading.value = false
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

  const setAlertArchived = async (row: ResearchAlertResponse, archived: boolean) => {
    const result = await runMutation(() => researchApi.setAlertArchived(
      row.id,
      { expectedVersion: row.version },
      archived,
    ))
    if (result) workbench.value.alerts = replaceById(workbench.value.alerts || [], result)
    await refreshTimeline()
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
    if (result === 'granted') window.dispatchEvent(new Event('heimdall:notification-permission'))
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
    archivedAlerts,
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
    setAlertArchived,
    acknowledgeEvent,
    requestDesktopPermission,
    evaluateAlerts,
  }
}
