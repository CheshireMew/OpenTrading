export const createPortfolioSaveState = () => {
  let dirty = false
  let version = 0

  return {
    isDirty: () => dirty,
    captureVersion: () => version,
    markDirty: () => {
      dirty = true
      version += 1
    },
    acknowledge: (savedVersion: number) => {
      if (version === savedVersion) dirty = false
    },
    clear: () => {
      dirty = false
      version = 0
    },
  }
}
