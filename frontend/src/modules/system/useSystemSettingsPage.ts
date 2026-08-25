import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import type {
  FredApiConfigResponse,
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

interface FredApiConfigForm {
  apiKeySet: boolean
  apiKeyPreview: string
  source: string
}

export const useSystemSettingsPage = () => {
  const { t } = useI18n()
  const systemConfig = ref<SystemConfigResponse | null>(null)
  const presets = ref<LlmProviderPresetResponse[]>([])
  const apiKeyDraft = ref('')
  const fredApiKeyDraft = ref('')
  const saving = ref(false)
  const fredSaving = ref(false)
  const message = ref('')
  const error = ref('')
  const fredMessage = ref('')
  const fredError = ref('')
  const systemLoading = ref(true)
  const llmLoading = ref(true)
  const fredLoading = ref(true)
  const systemLoadError = ref('')
  const llmLoadError = ref('')
  const fredLoadError = ref('')
  const form = reactive<LlmConfigForm>({
    provider: 'deepseek',
    apiKeySet: false,
    apiKeyPreview: '',
    baseUrl: '',
    modelId: '',
    reasoningEnabled: false,
  })
  const fredForm = reactive<FredApiConfigForm>({
    apiKeySet: false,
    apiKeyPreview: '',
    source: 'unset',
  })

  const selectedPreset = computed(() => presets.value.find((item) => item.id === form.provider) || null)
  const isCustomProvider = computed(() => form.provider === 'custom')
  const canSave = computed(() => {
    const hasApiKey = Boolean(apiKeyDraft.value || form.apiKeySet)
    if (!hasApiKey) return false
    if (isCustomProvider.value) return Boolean(form.baseUrl && form.modelId)
    return true
  })
  const canSaveFred = computed(() => Boolean(fredApiKeyDraft.value))

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

  const applyFredConfig = (config: FredApiConfigResponse) => {
    fredForm.apiKeySet = Boolean(config.apiKeySet)
    fredForm.apiKeyPreview = config.apiKeyPreview || ''
    fredForm.source = config.source || 'unset'
    fredApiKeyDraft.value = ''
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

  const loadFredConfig = async () => {
    fredLoading.value = true
    fredLoadError.value = ''
    try {
      applyFredConfig(await systemApi.getFredApiConfig())
    } catch (err) {
      console.error('Load FRED config failed', err)
      fredLoadError.value = t('settings.loadFailed')
    } finally {
      fredLoading.value = false
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

  const saveFredConfig = async () => {
    if (!canSaveFred.value) return
    fredSaving.value = true
    fredMessage.value = ''
    fredError.value = ''
    try {
      const response = await systemApi.updateFredApiConfig({
        apiKey: fredApiKeyDraft.value,
      })
      applyFredConfig(response)
      fredMessage.value = t('settings.fredSaved')
    } catch (err) {
      console.error('Save FRED API config failed', err)
      fredError.value = t('settings.fredSaveFailed')
    } finally {
      fredSaving.value = false
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

  const clearFredApiKey = async () => {
    if (!fredForm.apiKeySet || !window.confirm(t('settings.clearFredConfirm'))) return
    fredSaving.value = true
    fredMessage.value = ''
    fredError.value = ''
    try {
      applyFredConfig(await systemApi.updateFredApiConfig({ apiKey: '' }))
      fredMessage.value = t('settings.keyCleared')
    } catch (err) {
      console.error('Clear FRED API key failed', err)
      fredError.value = t('settings.clearFailed')
    } finally {
      fredSaving.value = false
    }
  }

  onMounted(() => {
    void Promise.all([loadSystemConfig(), loadLlmConfig(), loadFredConfig()])
  })

  return {
    systemConfig,
    presets,
    apiKeyDraft,
    fredApiKeyDraft,
    saving,
    fredSaving,
    message,
    error,
    fredMessage,
    fredError,
    systemLoading,
    llmLoading,
    fredLoading,
    systemLoadError,
    llmLoadError,
    fredLoadError,
    form,
    fredForm,
    selectedPreset,
    isCustomProvider,
    canSave,
    canSaveFred,
    applyProviderPreset,
    handleProviderChange,
    saveConfig,
    saveFredConfig,
    clearLlmApiKey,
    clearFredApiKey,
    loadSystemConfig,
    loadLlmConfig,
    loadFredConfig,
  }
}

