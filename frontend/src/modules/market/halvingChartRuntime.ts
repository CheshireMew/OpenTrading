export interface HalvingChartRuntime {
  Chart: typeof import('chart.js').Chart
}

let runtimePromise: Promise<HalvingChartRuntime> | null = null

export const loadHalvingChartRuntime = async (): Promise<HalvingChartRuntime> => {
  if (!runtimePromise) {
    runtimePromise = Promise.all([
      import('chart.js'),
      import('chartjs-plugin-annotation'),
      import('chartjs-adapter-date-fns'),
    ]).then(([chartJs, annotationPlugin]) => {
      chartJs.Chart.register(
        chartJs.LineController,
        chartJs.LineElement,
        chartJs.PointElement,
        chartJs.LinearScale,
        chartJs.LogarithmicScale,
        chartJs.TimeScale,
        chartJs.Tooltip,
        chartJs.Legend,
        chartJs.Decimation,
        annotationPlugin.default,
      )
      return { Chart: chartJs.Chart }
    })
  }
  return runtimePromise
}
