<template>
  <div class="cw-quantity-field" :class="{'cw-quantity-compact':compact}">
    <label>
      <span class="cw-quantity-label">{{ caption }}<output v-if="max !== undefined">{{ percent }}%</output></span>
      <span class="cw-quantity-input"><input type="text" inputmode="decimal" autocomplete="off" :aria-label="caption" :value="text" :aria-invalid="invalid || undefined" required @input="input" @blur="normalize" /><span v-if="compact && unit" class="cw-quantity-unit" aria-hidden="true">{{ unit }}</span></span>
    </label>
    <template v-if="max !== undefined">
      <input class="cw-quantity-slider" type="range" min="0" max="100" step="1" :value="percent" :aria-label="cw('replayQuantityPercent')" :aria-valuetext="percent + '%'" @input="selectPercent(Number(($event.target as HTMLInputElement).value))" />
      <div class="cw-quantity-stops"><button v-for="value in [0,25,50,75,100]" :key="value" type="button" @click="selectPercent(value)">{{ value }}%</button></div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { cw } from '@/modules/chartWorkspace/locale'
import { formatQuantity, quantityAtPercent, quantityPercent } from '@/modules/chartWorkspace/replayQuantity'

const props = defineProps<{ modelValue: number; max?: number; step?: number; label?: string; unit?: string; compact?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: number] }>()
const text = ref(formatQuantity(props.modelValue))
const caption = computed(() => (props.label ?? cw('replayQuantity')) + (props.unit ? ` (${props.unit})` : ''))
const parse = (value: string) => value.trim() === '' ? NaN : Number(value)
const percent = computed(() => quantityPercent(props.modelValue, props.max ?? 0))
const invalid = computed(() => !Number.isFinite(props.modelValue) || props.modelValue <= 0 || (props.max !== undefined && props.modelValue > props.max))
function input(event: Event) { text.value = (event.target as HTMLInputElement).value; emit('update:modelValue', parse(text.value)) }
function normalize() { text.value = formatQuantity(props.modelValue) }
function selectPercent(value: number) {
  const quantity = quantityAtPercent(props.max ?? 0, value, props.step ?? 0.00000001)
  text.value = formatQuantity(quantity); emit('update:modelValue', quantity)
}
watch(() => props.modelValue, value => { if (!Object.is(value, parse(text.value))) text.value = formatQuantity(value) })
watch(() => props.max, value => { if (value !== undefined && props.modelValue > value) emit('update:modelValue', value) })
</script>

<style scoped>
.cw-quantity-input{display:flex;position:relative;min-width:0;flex:1}.cw-quantity-unit{position:absolute;inset-inline-end:7px;top:50%;transform:translateY(-50%);color:var(--cw-muted,var(--ui-muted));font-size:10px;pointer-events:none}.cw-quantity-compact .cw-quantity-label{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%);white-space:nowrap}.cw-quantity-compact:has(.cw-quantity-unit) input{padding-inline-end:47px!important}
.cw-quantity-field{display:grid;gap:5px;min-width:0}.cw-quantity-field label{display:grid;gap:5px;min-width:0}.cw-quantity-label{display:flex;align-items:center;justify-content:space-between;gap:10px}.cw-quantity-label output{font-variant-numeric:tabular-nums;color:var(--cw-muted,var(--ui-muted));font-size:12px}.cw-quantity-field input:not([type=range]){width:100%;min-width:0;box-sizing:border-box;font-variant-numeric:tabular-nums}.cw-quantity-field .cw-quantity-slider{width:100%;min-height:20px;height:20px;padding:0;border:0;accent-color:var(--cw-accent,var(--ui-accent));cursor:pointer;background:transparent}.cw-quantity-stops{display:flex;justify-content:space-between;gap:3px}.cw-quantity-stops button{font-size:11px;min-height:24px;padding:2px!important;border:0!important;background:transparent!important;color:var(--cw-muted,var(--ui-muted))!important}.cw-quantity-stops button:hover{color:var(--cw-accent,var(--ui-accent))!important}
</style>
