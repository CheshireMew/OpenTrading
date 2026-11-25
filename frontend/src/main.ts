import { createApp } from 'vue'
import { createPinia } from 'pinia'
import './style.css'
import './styles/workspace-layouts.css'
import { applyImportedPreferences } from './modules/personal/browserPreferences'

async function start() {
  await applyImportedPreferences().catch(() => {})
  const [{ default: App }, { default: router }, { default: i18n }] = await Promise.all([import('./App.vue'), import('./router'), import('./i18n')])
  createApp(App).use(createPinia()).use(router).use(i18n).mount('#app')
}
void start()
