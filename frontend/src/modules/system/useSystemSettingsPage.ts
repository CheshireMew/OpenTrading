import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import type {
  LlmProviderConfigResponse,
  LlmProviderPresetResponse,
  SystemConfigResponse,
} from './contracts'
import { systemApi } from './api'

interface LlmConfigForm {
  provider: string
  apiKeySet: boolean
  apiKeyPreview: string
  baseUrl: string
  modelId: string
  reasoningEnabled: boolean
}

export const useSystemSettingsPage = () => {
  const { t } = useI18n()
  const systemConfig = ref<SystemConfigResponse | null>(null)
  const presets = ref<LlmProviderPresetResponse[]>([])
  const apiKeyDraft = ref('')
  const saving = ref(false)
  const message = ref('')
  const error = ref('')
  const systemLoading = ref(true)
  const llmLoading = ref(true)
  const systemLoadError = ref('')
  const llmLoadError = ref('')
  const form = reactive<LlmConfigForm>({
    provider: 'deepseek',
    apiKeySet: false,
    apiKeyPreview: '',
    baseUrl: '',
    modelId: '',
    reasoningEnabled: false,
  })

  const selectedPreset = computed(() => presets.value.find((item) => item.id === form.provider) || null)
  const isCustomProvider = computed(() => form.provider === 'custom')
  const canSave = computed(() => {
    const hasApiKey = Boolean(apiKeyDraft.value || form.apiKeySet)
    if (!hasApiKey) return false
    if (isCustomProvider.value) return Boolean(form.baseUrl && form.modelId)
    return true
  })

  const applyConfig = (config: LlmProviderConfigResponse) => {
    presets.value = config.presets || []
    form.provider = config.provider || 'deepseek'
    form.apiKeySet = Boolean(config.apiKeySet)
    form.apiKeyPreview = config.apiKeyPreview || ''
    form.baseUrl = config.baseUrl || ''
    form.modelId = config.modelId || ''
    form.reasoningEnabled = Boolean(config.reasoningEnabled)
    apiKeyDraft.value = ''
  }

  const applyProviderPreset = () => {
    if (form.provider !== 'deepseek') form.reasoningEnabled = false
    if (isCustomProvider.value) {
      form.baseUrl = ''
      form.modelId = ''
      return
    }
    const preset = selectedPreset.value
    if (!preset) return
    form.baseUrl = preset.baseUrl
    form.modelId = form.provider === 'deepseek' && form.reasoningEnabled ? 'deepseek-reasoner' : preset.defaultModel
  }

  const handleProviderChange = () => {
    applyProviderPreset()
  }

  const loadSystemConfig = async () => {
    systemLoading.value = true
    systemLoadError.value = ''
    try {
      systemConfig.value = await systemApi.getConfig()
    } catch (err) {
      console.error('Load system config failed', err)
      systemLoadError.value = t('settings.loadFailed')
    } finally {
      systemLoading.value = false
    }
  }

  const loadLlmConfig = async () => {
    llmLoading.value = true
    llmLoadError.value = ''
    try {
      applyConfig(await systemApi.getLlmConfig())
    } catch (err) {
      console.error('Load LLM config failed', err)
      llmLoadError.value = t('settings.loadFailed')
    } finally {
      llmLoading.value = false
    }
  }

  const saveConfig = async () => {
    if (!canSave.value) return
    saving.value = true
    message.value = ''
    error.value = ''
    try {
      const response = await systemApi.updateLlmConfig({
        provider: form.provider,
        apiKey: apiKeyDraft.value || null,
        baseUrl: form.baseUrl,
        modelId: form.modelId,
        reasoningEnabled: form.reasoningEnabled,
      })
      applyConfig(response)
      message.value = t('settings.saved')
    } catch (err) {
      console.error('Save LLM config failed', err)
      error.value = t('settings.saveFailed')
    } finally {
      saving.value = false
    }
  }

  const clearLlmApiKey = async () => {
    if (!form.apiKeySet || !window.confirm(t('settings.clearLlmConfirm'))) return
    saving.value = true
    message.value = ''
    error.value = ''
    try {
      applyConfig(await systemApi.updateLlmConfig({
        provider: form.provider,
        apiKey: '',
        baseUrl: form.baseUrl,
        modelId: form.modelId,
        reasoningEnabled: form.reasoningEnabled,
      }))
      message.value = t('settings.keyCleared')
    } catch (err) {
      console.error('Clear LLM API key failed', err)
      error.value = t('settings.clearFailed')
    } finally {
      saving.value = false
    }
  }

  onMounted(() => {
    void Promise.all([loadSystemConfig(), loadLlmConfig()])
  })

  return {
    systemConfig,
    presets,
    apiKeyDraft,
    saving,
    message,
    error,
    systemLoading,
    llmLoading,
    systemLoadError,
    llmLoadError,
    form,
    selectedPreset,
    isCustomProvider,
    canSave,
    applyProviderPreset,
    handleProviderChange,
    saveConfig,
    clearLlmApiKey,
    loadSystemConfig,
    loadLlmConfig,
  }
}

