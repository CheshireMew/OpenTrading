<template><article class="app-markdown" v-html="html" /></template>

<script setup lang="ts">
import { computed } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'

const props = defineProps<{ source: string }>()
const html = computed(() => DOMPurify.sanitize(marked.parse(props.source, { async:false, gfm:true }) as string))
</script>

<style scoped>
.app-markdown { min-width:0; color:var(--ui-text); font-size:14px; line-height:1.8; overflow-wrap:anywhere; }
.app-markdown :deep(> :first-child) { margin-top:0; }
.app-markdown :deep(> :last-child) { margin-bottom:0; }
.app-markdown :deep(h1),.app-markdown :deep(h2),.app-markdown :deep(h3),.app-markdown :deep(h4) { color:var(--ui-title); font-weight:600; line-height:1.4; margin:1.5em 0 .65em; }
.app-markdown :deep(h1) { font-size:24px; }
.app-markdown :deep(h2) { font-size:20px; border-bottom:1px solid var(--ui-border); padding-bottom:.4em; }
.app-markdown :deep(h3) { font-size:17px; }
.app-markdown :deep(p),.app-markdown :deep(ul),.app-markdown :deep(ol),.app-markdown :deep(blockquote),.app-markdown :deep(pre),.app-markdown :deep(table) { margin:0 0 1em; }
.app-markdown :deep(ul),.app-markdown :deep(ol) { padding-left:1.5em; }
.app-markdown :deep(ul) { list-style:disc; }
.app-markdown :deep(ol) { list-style:decimal; }
.app-markdown :deep(li > ul),.app-markdown :deep(li > ol) { margin-bottom:0; }
.app-markdown :deep(a) { color:var(--ui-accent); text-decoration:underline; text-underline-offset:3px; }
.app-markdown :deep(blockquote) { border-left:3px solid var(--ui-borderStrong); padding-left:1em; color:var(--ui-muted); }
.app-markdown :deep(pre) { overflow-x:auto; border:1px solid var(--ui-border); padding:12px; background:var(--ui-toolbar); border-radius:5px; }
.app-markdown :deep(code) { font-family:Consolas,monospace; font-size:.9em; padding:2px 4px; background:var(--ui-elevated); border-radius:3px; }
.app-markdown :deep(pre code) { padding:0; background:none; }
.app-markdown :deep(table) { display:block; max-width:100%; overflow-x:auto; border-collapse:collapse; font-variant-numeric:tabular-nums; }
.app-markdown :deep(th),.app-markdown :deep(td) { border:1px solid var(--ui-border); padding:8px 12px; text-align:left; }
.app-markdown :deep(th) { background:var(--ui-toolbar); font-weight:600; white-space:nowrap; }
.app-markdown :deep(hr) { margin:24px 0; border-color:var(--ui-border); }
.app-markdown :deep(img) { max-width:100%; height:auto; }
</style>
