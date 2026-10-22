import { DARK_PALETTE } from '@/theme/palette.mjs'
import { nextTick, onBeforeUnmount, ref, type Ref } from 'vue'
import { Chart, registerables } from 'chart.js'

import { useMoney } from '@/composables/useMoney'
import type { DCAResponse } from './contracts'


Chart.register(...registerables)

interface UseDcaChartsOptions {
  theme: Ref<string>
  t: (key: string) => string
  result: Ref<DCAResponse | null>
}

export const useDcaCharts = ({
  theme,
  t,
  result,
}: UseDcaChartsOptions) => {
  const { displayCurrency, toDisplayAmount, formatMoney } = useMoney()
  const roiChartCanvas = ref<HTMLCanvasElement | null>(null)
  const priceChartCanvas = ref<HTMLCanvasElement | null>(null)
  const investmentChartCanvas = ref<HTMLCanvasElement | null>(null)

  let roiChart: Chart | null = null
  let priceChart: Chart | null = null
  let investmentChart: Chart | null = null

  const parsedY = (value: number | null | undefined) => value ?? 0

  const destroyCharts = () => {
    roiChart?.destroy()
    priceChart?.destroy()
    investmentChart?.destroy()
    roiChart = null
    priceChart = null
    investmentChart = null
  }

  const renderCharts = () => {
    if (!result.value?.history) return

    const history = result.value.history
    const sourceCurrency = result.value.pricing_currency || 'USDT'
    const labels = history.map((item) => item.date)
    const isDark = theme.value === 'dark'
    const textColor = isDark ? DARK_PALETTE.muted : '#6b7280'
    const gridColor = isDark ? DARK_PALETTE.grid : '#e5e7eb'

    nextTick(() => {
      if (roiChartCanvas.value) {
        roiChart?.destroy()
        const ctx = roiChartCanvas.value.getContext('2d')
        const roiData = history.map((item) => item.roi)
        if (ctx) {
          roiChart = new Chart(ctx, {
            type: 'line',
            data: {
              labels,
              datasets: [{
                label: 'ROI (%)',
                data: roiData,
                borderColor: (context) => (parsedY(context.parsed?.y) >= 0 ? 'rgb(16, 185, 129)' : 'rgb(239, 68, 68)'),
                backgroundColor: (context) => (parsedY(context.parsed?.y) >= 0 ? 'rgba(16, 185, 129, 0.15)' : 'rgba(239, 68, 68, 0.15)'),
                segment: {
                  borderColor: (context) => (parsedY(context.p1.parsed.y) >= 0 ? 'rgb(16, 185, 129)' : 'rgb(239, 68, 68)'),
                  backgroundColor: (context) => (parsedY(context.p1.parsed.y) >= 0 ? 'rgba(16, 185, 129, 0.15)' : 'rgba(239, 68, 68, 0.15)'),
                },
                fill: true,
                tension: 0.4,
                pointRadius: 0,
              }],
            },
            options: {
              responsive: true,
              maintainAspectRatio: false,
              plugins: {
                legend: { display: false },
                tooltip: {
                  callbacks: {
                    label: (context) => `ROI: ${parsedY(context.parsed.y).toFixed(2)}%`,
                  },
                  backgroundColor: isDark ? DARK_PALETTE.elevated : 'rgba(255, 255, 255, 0.9)',
                  titleColor: isDark ? '#fff' : '#000',
                  bodyColor: isDark ? '#fff' : '#000',
                  borderColor: gridColor,
                  borderWidth: 1,
                },
              },
              scales: {
                x: {
                  display: true,
                  ticks: { maxTicksLimit: 6, color: textColor, font: { size: 10 } },
                  grid: { color: gridColor, display: false },
                },
                y: {
                  display: true,
                  ticks: { color: textColor, font: { size: 10 } },
                  grid: { color: gridColor },
                },
              },
            },
          })
        }
      }

      if (priceChartCanvas.value) {
        priceChart?.destroy()
        const ctx = priceChartCanvas.value.getContext('2d')
        if (ctx) {
          priceChart = new Chart(ctx, {
            type: 'line',
            data: {
              labels,
              datasets: [
                {
                  label: t('dca.btcPrice'),
                  data: history.map((item) => toDisplayAmount(item.price, sourceCurrency) ?? 0),
                  borderColor: 'rgb(59, 130, 246)',
                  backgroundColor: 'rgba(59, 130, 246, 0.1)',
                  tension: 0.4,
                  pointRadius: 0,
                  yAxisID: 'y',
                },
                {
                  label: t('dca.averageCost'),
                  data: history.map((item) => toDisplayAmount(item.avg_cost, sourceCurrency) ?? 0),
                  borderColor: 'rgb(251, 191, 36)',
                  backgroundColor: 'rgba(251, 191, 36, 0.1)',
                  tension: 0.4,
                  pointRadius: 0,
                  yAxisID: 'y',
                },
              ],
            },
            options: {
              responsive: true,
              maintainAspectRatio: false,
              interaction: { mode: 'index', intersect: false },
              plugins: {
                legend: {
                  display: true,
                  labels: { color: textColor, boxWidth: 20 },
                },
                tooltip: {
                  backgroundColor: isDark ? DARK_PALETTE.elevated : 'rgba(255, 255, 255, 0.9)',
                  titleColor: isDark ? '#fff' : '#000',
                  bodyColor: isDark ? '#fff' : '#000',
                  borderColor: gridColor,
                  borderWidth: 1,
                  callbacks: {
                    label: (context) => `${context.dataset.label}: ${formatMoney(context.parsed.y, displayCurrency.value)}`,
                  },
                },
              },
              scales: {
                x: {
                  ticks: { maxTicksLimit: 6, color: textColor, font: { size: 10 } },
                  grid: { color: gridColor, display: false },
                },
                y: {
                  type: 'linear',
                  display: true,
                  position: 'left',
                  ticks: { color: textColor, font: { size: 10 } },
                  grid: { color: gridColor },
                },
              },
            },
          })
        }
      }

      if (investmentChartCanvas.value) {
        investmentChart?.destroy()
        const ctx = investmentChartCanvas.value.getContext('2d')
        if (ctx) {
          investmentChart = new Chart(ctx, {
            type: 'bar',
            data: {
              labels,
              datasets: [{
                label: t('dca.investAmount'),
                data: history.map((item, index) => toDisplayAmount(item.invested - (history[index - 1]?.invested || 0), sourceCurrency) ?? 0),
                backgroundColor: 'rgba(167, 139, 250, 0.6)',
                borderColor: 'rgb(167, 139, 250)',
                borderWidth: 0,
              }],
            },
            options: {
              responsive: true,
              maintainAspectRatio: false,
              plugins: {
                legend: { display: false },
                tooltip: {
                  callbacks: {
                    label: (context) => `${t('dca.invested')}: ${formatMoney(context.parsed.y, displayCurrency.value)}`,
                  },
                  backgroundColor: isDark ? DARK_PALETTE.elevated : 'rgba(255, 255, 255, 0.9)',
                  titleColor: isDark ? '#fff' : '#000',
                  bodyColor: isDark ? '#fff' : '#000',
                  borderColor: gridColor,
                  borderWidth: 1,
                },
              },
              scales: {
                x: {
                  ticks: { maxTicksLimit: 6, color: textColor, font: { size: 10 } },
                  grid: { color: gridColor, display: false },
                },
                y: {
                  ticks: { color: textColor, font: { size: 10 } },
                  grid: { color: gridColor },
                },
              },
            },
          })
        }
      }
    })
  }

  onBeforeUnmount(() => {
    destroyCharts()
  })

  return {
    roiChartCanvas,
    priceChartCanvas,
    investmentChartCanvas,
    renderCharts,
  }
}

