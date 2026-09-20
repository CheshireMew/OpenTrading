import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'

const DEV_FRONTEND_HOST = process.env.HEIMDALL_FRONTEND_HOST ?? '127.0.0.1'
const DEV_FRONTEND_PORT = Number(process.env.HEIMDALL_FRONTEND_PORT ?? 4173)
const DEV_API_HOST = process.env.HEIMDALL_API_HOST ?? '127.0.0.1'
const DEV_API_PORT = Number(process.env.HEIMDALL_API_PORT ?? 8000)
const DEV_API_TARGET = `http://${DEV_API_HOST}:${DEV_API_PORT}`

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    host: DEV_FRONTEND_HOST,
    port: DEV_FRONTEND_PORT,
    strictPort: true,
    proxy: {
      '/api': {
        target: DEV_API_TARGET,
        changeOrigin: true,
        ws: true,
        // rewrite: (path) => path.replace(/^\/api/, ''), // FastAPI有/api前缀，不需要rewrite
      }
    }
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules')) {
            if (id.includes('lightweight-charts')) {
              return 'lightweight-charts-vendor'
            }
            if (
              id.includes('chart.js') ||
              id.includes('chartjs-adapter-date-fns') ||
              id.includes('chartjs-plugin-annotation') ||
              id.includes('date-fns')
            ) {
              return 'chartjs-vendor'
            }
            if (id.includes('echarts') || id.includes('vue-echarts')) {
              return 'echarts-vendor'
            }
            if (
              id.includes('vue') ||
              id.includes('vue-router') ||
              id.includes('pinia') ||
              id.includes('vue-i18n')
            ) {
              return 'vue-vendor'
            }
            if (id.includes('@heroicons')) {
              return 'icons-vendor'
            }
            return 'vendor'
          }
        },
      },
    },
  }
})
