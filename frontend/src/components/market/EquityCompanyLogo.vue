<template>
  <span
    aria-hidden="true"
    class="inline-flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden rounded-lg"
    :class="src && !failed ? '' : 'bg-stone-100 ring-1 ring-stone-200 dark:bg-slate-700 dark:ring-slate-600'"
  >
    <img
      v-if="src && !failed"
      :src="src"
      alt=""
      width="40"
      height="40"
      loading="lazy"
      decoding="async"
      referrerpolicy="no-referrer"
      class="h-full w-full object-contain"
      @error="failed = true"
    />
    <span v-else class="text-xs font-semibold uppercase text-stone-500 dark:text-slate-300">{{ initials }}</span>
  </span>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'

const props = defineProps<{
  src?: string | null
  ticker: string
}>()

const failed = ref(false)
const initials = computed(() => props.ticker.replace(/[^a-z0-9]/gi, '').slice(0, 2) || '?')

watch(() => props.src, () => { failed.value = false })
</script>
