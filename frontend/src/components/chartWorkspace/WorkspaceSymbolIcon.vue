<template>
  <span class="symbol-avatar" :class="{ 'symbol-avatar-image': imageVisible }" aria-hidden="true">
    <img v-if="imageVisible" :key="url" :src="url" alt="" width="20" height="20" decoding="async" @error="imageFailed" />
    <span v-else>{{ base.slice(0, 2) }}</span>
  </span>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { ChartSymbol } from '@/modules/chartWorkspace/api'
import { symbolAssetCode, symbolIconUrl } from '@/modules/chartWorkspace/symbolIcons'

const props = defineProps<{ symbol?: ChartSymbol; fallback: string }>()
const base = computed(() => symbolAssetCode(props.symbol, props.fallback))
const url = computed(() => symbolIconUrl(props.symbol, props.fallback)), failedUrl = ref('')
const imageVisible = computed(() => !!url.value && url.value !== failedUrl.value)
function imageFailed(event: Event) { failedUrl.value = (event.target as HTMLImageElement).getAttribute('src') ?? '' }
</script>

<style scoped>
.symbol-avatar { display: inline-flex; align-items: center; justify-content: center; flex: 0 0 20px; width: 20px; height: 20px; overflow: hidden; border-radius: 50%; font-size: 8px; font-weight: 650; line-height: 1; background:var(--ui-elevated);color:var(--ui-muted);vertical-align:middle }
.symbol-avatar-image{background:transparent;border-radius:0;overflow:visible}
.symbol-avatar img{display:block;width:100%;height:100%;object-fit:contain;object-position:center}
</style>
