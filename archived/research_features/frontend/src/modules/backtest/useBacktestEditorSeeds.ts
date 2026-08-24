import { supportsVersionEditing } from './templateRuntime'
import type { UseBacktestEditorSeedsOptions } from './editorTypes'

export const useBacktestEditorSeeds = ({
  route,
  router,
  config,
  strategies,
  selectedStrategy,
  selectedVersion,
  editor,
  syncStrategyVersion,
}: UseBacktestEditorSeedsOptions) => {
  const canCopySelectedStrategy = () => supportsVersionEditing(selectedStrategy.value)

  const prepareCopyDraft = () => {
    if (!selectedStrategy.value || !selectedVersion.value) return
    if (!canCopySelectedStrategy()) {
      prepareBlankDraft()
      return
    }
    editor.fillVersionDraft()
    editor.showVersionEditor.value = true
  }

  const prepareBlankDraft = () => {
    editor.startBlankBuilder()
    editor.showVersionEditor.value = true
    editor.versionDraft.key = config.strategy_key || editor.versionDraft.key
  }

  const syncRouteFromSelection = async (mode: 'copy' | 'blank') => {
    await router.replace({
      path: '/backtest/editor',
      query: {
        mode,
        strategy: config.strategy_key,
        ...(mode === 'copy' ? { version: String(config.strategy_version) } : {}),
      },
    })
  }

  const applyRouteSeed = () => {
    const strategyKey = typeof route.query.strategy === 'string' ? route.query.strategy : ''
    const version = Number(route.query.version)
    const mode = route.query.mode === 'blank' ? 'blank' : 'copy'

    if (strategyKey && strategies.value.find((item) => item.key === strategyKey)) {
      config.strategy_key = strategyKey
    }
    syncStrategyVersion()

    if (Number.isFinite(version) && version > 0) {
      config.strategy_version = version
      syncStrategyVersion()
    }

    if (mode === 'blank') {
      prepareBlankDraft()
      return
    }

    prepareCopyDraft()
  }

  const openCopySeed = async () => {
    await syncRouteFromSelection('copy')
    prepareCopyDraft()
  }

  const openBlankSeed = async () => {
    await syncRouteFromSelection('blank')
    prepareBlankDraft()
  }

  const goBackToCenter = () => {
    router.push('/backtest')
  }

  return {
    applyRouteSeed,
    openCopySeed,
    openBlankSeed,
    goBackToCenter,
  }
}

