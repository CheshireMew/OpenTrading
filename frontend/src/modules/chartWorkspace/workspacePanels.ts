import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

export function useWorkspacePanels(deps: { dirty: () => void; resizeChart: () => void }) {
  const rightOpen = ref(true), rightWidth = ref(300), bottomHeight = ref(340), bottomTab = ref('')
  const editorMounted = ref(false), testerMounted = ref(false), compactWorkspace = ref(false)
  const watchlistDrawerOpen = ref(false), maxBottomHeight = ref(700)
  const watchlistVisible = computed(() => compactWorkspace.value ? watchlistDrawerOpen.value : rightOpen.value)
  const resizeChart = () => void nextTick(deps.resizeChart)
  let stopDrag: (() => void) | undefined
  function toggleWatchlist() {
    if (compactWorkspace.value) watchlistDrawerOpen.value = !watchlistDrawerOpen.value
    else rightOpen.value = !rightOpen.value
  }
  function syncViewport() {
    compactWorkspace.value = window.innerWidth <= 950
    maxBottomHeight.value = Math.max(180, window.innerHeight - 180)
    if (!compactWorkspace.value) watchlistDrawerOpen.value = false
    bottomHeight.value = Math.min(bottomHeight.value, maxBottomHeight.value)
  }
  function resize(start: PointerEvent, update: (dx: number, dy: number) => void) {
    stopDrag?.()
    const x = start.clientX, y = start.clientY
    const move = (event: PointerEvent) => update(event.clientX - x, event.clientY - y)
    const stop = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', stop); stopDrag = undefined; deps.dirty() }
    stopDrag = stop
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', stop, { once: true })
    start.preventDefault()
  }
  function resizeRight(event: PointerEvent) { const width = rightWidth.value; resize(event, dx => { rightWidth.value = Math.max(240, Math.min(520, width - dx)) }) }
  function resizeBottom(event: PointerEvent) { const height = bottomHeight.value; resize(event, (_, dy) => { bottomHeight.value = Math.max(180, Math.min(window.innerHeight - 180, height - dy)) }) }
  const toggleBottom = (tab: string) => { bottomTab.value = bottomTab.value === tab ? '' : tab }
  function snapshot() { return { rightWidth: rightWidth.value, rightOpen: rightOpen.value, bottomHeight: bottomHeight.value } }
  function restore(data: Record<string, any>) {
    rightWidth.value = data.rightWidth ?? 300
    rightOpen.value = data.rightOpen ?? true
    bottomHeight.value = data.bottomHeight ?? 340
  }
  watch(bottomTab, value => { if (value === 'editor') editorMounted.value = true; if (value === 'tester') testerMounted.value = true; resizeChart() })
  watch([rightOpen, rightWidth, bottomHeight], () => { deps.dirty(); resizeChart() })
  onMounted(() => { syncViewport(); window.addEventListener('resize', syncViewport) })
  onBeforeUnmount(() => { stopDrag?.(); window.removeEventListener('resize', syncViewport) })
  return { rightOpen, rightWidth, bottomHeight, bottomTab, editorMounted, testerMounted, compactWorkspace,
    watchlistDrawerOpen, maxBottomHeight, watchlistVisible,
    toggleWatchlist, toggleBottom, resizeRight, resizeBottom, snapshot, restore }
}
