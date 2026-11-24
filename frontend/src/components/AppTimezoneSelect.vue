<template>
  <select
    :id="id"
    :value="selectedValue"
    :aria-label="ariaLabel"
    class="app-control w-full px-3 py-2"
    @change="handleChange"
  >
    <option v-for="option in options" :key="option.value" :value="option.value">
      {{ option.label }}
    </option>
  </select>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useUserPreferences } from '@/composables/useUserPreferences'
import { useI18n } from 'vue-i18n'

const props = defineProps<{
  modelValue?: string
  id?: string
  ariaLabel?: string
}>()
const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const { timezone, timezoneOptions, setTimezone } = useUserPreferences()
const { t, te } = useI18n()

const selectedValue = computed(() => props.modelValue ?? timezone.value)
const options = computed(() => {
  const values = timezoneOptions.value.some(option => option.value === selectedValue.value) ? timezoneOptions.value
    : [{ value: selectedValue.value, label: selectedValue.value }, ...timezoneOptions.value]
  return values.map(option => {
    const key = 'settings.timezoneNames.' + option.value
    return { ...option, label: te(key) ? t(key) : option.label }
  })
})

const handleChange = (event: Event) => {
  const value = (event.target as HTMLSelectElement).value
  emit('update:modelValue', value)
  if (props.modelValue === undefined) {
    setTimezone(value)
  }
}
</script>
