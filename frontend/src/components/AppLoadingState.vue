<template>
  <div class="app-loading-state" role="status" aria-live="polite" :aria-label="label">
    <span class="sr-only">{{ label }}</span>
    <div v-for="row in rows" :key="row" class="app-skeleton-row" aria-hidden="true">
      <span class="app-skeleton-line" /><span class="app-skeleton-line" /><span class="app-skeleton-line" />
    </div>
  </div>
</template>
<script setup lang="ts">
withDefaults(defineProps<{ label: string; rows?: number }>(), { rows: 5 })
</script>
