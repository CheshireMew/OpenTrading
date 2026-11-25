import { computed, ref, watch, type Ref } from 'vue'
import { chartApi, type ChartQuote, type WorkspaceDocument } from './api'
import { deleteDraft, readDraft, writeDraft } from './drafts'
import { cw } from './locale'

const createWatchlistState = () => ({
  watchlists: ref<WorkspaceDocument[]>([]),
  selectedId: ref<string | null>(null),
  pendingWatch: ref<string[]>([]),
  quotes: ref<Record<string, ChartQuote>>({}),
  saveQueue: Promise.resolve(),
})

const sharedState = createWatchlistState()

export function createWorkspaceWatchlists(deps: {
  activeSymbolId: Readonly<Ref<string>>
  requestName: (title: string, value: string) => Promise<string | null>
  onError: (error: unknown) => void
}, state = createWatchlistState()) {
  const { watchlists, selectedId, pendingWatch, quotes } = state
  const watchlistId = computed({
    get: () => selectedId.value ?? watchlists.value[0]?.id ?? 'default',
    set: (id: string) => { selectedId.value = id },
  })
  const dragIndex = ref(-1)
  const managing = ref(false)
  const watchlist = computed(() => watchlists.value.find(list => list.id === watchlistId.value))
  const watchSymbols = computed(() => (watchlist.value?.data.symbols as string[] | undefined) ?? [])
  let disposed = false, paused = false, quoteEpoch = 0
  let timer: ReturnType<typeof setTimeout> | undefined
  async function refreshQuotes() {
    clearTimeout(timer)
    if (disposed || paused) return
    const epoch = ++quoteEpoch, keys = [...new Set([...watchSymbols.value, deps.activeSymbolId.value])]
    try {
      for (let i = 0; i < keys.length; i += 100) {
        const data = await chartApi.quotes(keys.slice(i, i + 100))
        if (disposed || paused || epoch !== quoteEpoch) return
        for (const quote of data) quotes.value[quote.id] = quote
      }
    } catch (error) { if (!disposed && !paused && epoch === quoteEpoch) deps.onError(error) }
    finally { if (!disposed && !paused && epoch === quoteEpoch) timer = setTimeout(refreshQuotes, 5000) }
  }
  async function persistWatch(items: string[]) {
    const list = watchlist.value
    if (!list || disposed || managing.value) return
    list.data = { ...list.data, symbols: [...items] }
    pendingWatch.value = [...new Set([...pendingWatch.value, list.id])]
    const data = { ...list.data }
    const operation = state.saveQueue.then(async () => {
      await writeDraft('watch:' + list.id, { version: list.version, data, pending: true })
      try {
        const saved = await chartApi.save('watchlists', list.id, { name: list.name, data, expected_version: list.version })
        list.version = saved.version
        const pending = JSON.stringify(data) !== JSON.stringify(list.data)
        await writeDraft('watch:' + list.id, { version: list.version, data: list.data, pending })
        if (!pending) pendingWatch.value = pendingWatch.value.filter(id => id !== list.id)
        if (!disposed) void refreshQuotes()
      } catch (error) { if (!disposed) deps.onError(error) }
    })
    state.saveQueue = operation.catch(deps.onError)
    await operation
  }
  const removeWatch = (id: string) => void persistWatch(watchSymbols.value.filter(key => key !== id))
  function moveWatch(index: number) {
    if (dragIndex.value < 0) return
    const list = [...watchSymbols.value], item = list.splice(dragIndex.value, 1)[0]
    if (item) list.splice(index, 0, item)
    dragIndex.value = -1
    void persistWatch(list)
  }
  async function newWatchlist() {
    const name = await deps.requestName(cw('watchlistName'), cw('newWatchlist'))
    if (!name || disposed) return
    const operation = state.saveQueue.then(async () => {
      const list = await chartApi.save('watchlists', crypto.randomUUID(), { name, data: { symbols: [] }, expected_version: 0 })
      watchlists.value.push(list)
      if (!disposed) watchlistId.value = list.id
    })
    state.saveQueue = operation.catch(error => { if (!disposed) deps.onError(error) })
    await state.saveQueue
  }
  async function renameWatchlist() {
    const list = watchlist.value
    if (!list) return
    const name = await deps.requestName(cw('watchlistName'), list.name)
    if (!name || disposed) return
    // Use the same queue as content saves so both observe the latest version.
    const operation = state.saveQueue.then(async () => {
      const saved = await chartApi.save('watchlists', list.id, { name, data: list.data, expected_version: list.version })
      list.name = saved.name
      list.version = saved.version
    })
    state.saveQueue = operation.catch(deps.onError)
    await state.saveQueue
  }
  async function deleteWatchlist() {
    const list=watchlist.value
    if(!list||managing.value)return
    managing.value=true
    const operation=state.saveQueue.then(async()=>{
      await chartApi.remove('watchlists',list.id,list.version)
      await deleteDraft('watch:'+list.id)
      watchlists.value=watchlists.value.filter(item=>item.id!==list.id)
      pendingWatch.value=pendingWatch.value.filter(id=>id!==list.id)
      if(selectedId.value===list.id||!watchlists.value.some(item=>item.id===watchlistId.value))selectedId.value=watchlists.value[0]?.id??null
      void refreshQuotes()
    })
    state.saveQueue=operation.catch(deps.onError)
    try{await state.saveQueue}finally{managing.value=false}
  }
  async function initialize(lists: WorkspaceDocument[], queue = state.saveQueue) {
    if (disposed) return false
    const pending: string[] = []
    let conflict = false
    for (const list of lists) {
      const draft = await readDraft<{ version: number; data: Record<string, unknown>; pending: boolean }>('watch:' + list.id)
      if (disposed || queue !== state.saveQueue) return false
      if (!draft?.pending) continue
      if (draft.version === list.version) { list.data = draft.data; pending.push(list.id) }
      else conflict = true
    }
    watchlists.value = lists
    pendingWatch.value = pending
    if (selectedId.value && !lists.some(list => list.id === selectedId.value)) selectedId.value = null
    if (conflict) deps.onError(new Error(cw('watchConflict')))
    return true
  }
  async function loadWatchlists() {
    // A route change can happen before a queued write reaches the server.
    while (!disposed) {
      const queue = state.saveQueue
      await queue
      if (disposed) return
      const lists = await chartApi.documents('watchlists')
      if (queue === state.saveQueue && await initialize(lists, queue)) return
    }
  }
  function restoreSelection(id: string, preserveCurrent = false) {
    if (preserveCurrent && selectedId.value !== null) return
    if (watchlists.value.some(list => list.id === id)) selectedId.value = id
  }
  const stopWatch = watch(watchlistId, () => void refreshQuotes())
  function pause() { paused = true; quoteEpoch++; clearTimeout(timer) }
  function resume() { if (!disposed && paused) { paused = false; void refreshQuotes() } }
  function dispose() { disposed = true; quoteEpoch++; clearTimeout(timer); stopWatch() }
  return { watchlists, watchlistId, watchlist, watchSymbols, pendingWatch, quotes, dragIndex, managing, deleteWatchlist,
    persistWatch, removeWatch, moveWatch, newWatchlist, renameWatchlist, refreshQuotes, initialize, loadWatchlists, restoreSelection, pause, resume, dispose }
}

export const createSharedWorkspaceWatchlists = (deps: Parameters<typeof createWorkspaceWatchlists>[0]) =>
  createWorkspaceWatchlists(deps, sharedState)

export type WorkspaceWatchlists = ReturnType<typeof createWorkspaceWatchlists>
