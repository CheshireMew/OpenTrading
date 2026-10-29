<template>
  <div class="app-empty-state">
    <component :is="icon" v-if="icon" class="app-empty-icon" aria-hidden="true" />
    <h2 class="app-section-title">{{ title }}</h2>
    <p v-if="description" class="app-subtitle">{{ description }}</p>
    <div v-if="$slots.default" class="app-empty-actions"><slot /></div>
  </div>
</template>
<script setup lang="ts">
import type { Component } from 'vue'
defineProps<{ title: string; description?: string; icon?: Component }>()
</script>
