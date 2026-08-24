export const chartTextColor = (dark: boolean) => (dark ? '#9ca3af' : '#6b7280')

export const chartAxisLineColor = (dark: boolean) => (dark ? '#374151' : '#d1d5db')

export const chartSplitLineColor = (dark: boolean) => (dark ? '#374151' : '#e5e7eb')

export const categoryAxis = (dark: boolean, data: Array<string | number>, axisLabel: Record<string, unknown> = {}) => ({
  type: 'category',
  data,
  axisLabel: { color: chartTextColor(dark), ...axisLabel },
  axisLine: { lineStyle: { color: chartAxisLineColor(dark) } },
})

export const valueAxis = (dark: boolean) => ({
  type: 'value',
  axisLabel: { color: chartTextColor(dark) },
  splitLine: { lineStyle: { color: chartSplitLineColor(dark) } },
})

export const chartGrid = ({ top = 16 }: { top?: number } = {}) => ({
  left: 16,
  right: 16,
  top,
  bottom: 16,
  containLabel: true,
})
