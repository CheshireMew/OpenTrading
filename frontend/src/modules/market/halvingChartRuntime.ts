export interface HalvingChartRuntime {
  Chart: typeof import('chart.js').Chart
}

let runtimePromise: Promise<HalvingChartRuntime> | null = null

export const loadHalvingChartRuntime = async (): Promise<HalvingChartRuntime> => {
  if (!runtimePromise) {
    runtimePromise = import('@/utils/chartJsRuntime')
  }
  return runtimePromise
}
