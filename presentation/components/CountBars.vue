<script setup lang="ts">
import { computed } from 'vue'
import { formatNumber } from '../data'

const props = withDefaults(defineProps<{
  items: { label: string, value: number }[]
  columns?: boolean
  highlight?: string[]
  height?: string
}>(), { columns: false, highlight: () => [], height: '10rem' })

const max = computed(() => Math.max(...props.items.map(item => item.value)))
const labelEvery = computed(() => Math.ceil(props.items.length / 8))
</script>

<template>
  <div v-if="props.columns" class="columns" :style="{ height: props.height }">
    <div v-for="(item, index) in props.items" :key="item.label" class="col" :title="`${item.label}: ${formatNumber(item.value)}`">
      <span class="bar" :style="{ height: `${(item.value / max) * 100}%` }" />
      <span class="tick mono">{{ index % labelEvery === 0 ? item.label.slice(5) : '' }}</span>
    </div>
  </div>
  <div v-else class="rows">
    <div v-for="item in props.items" :key="item.label" class="row" :title="`${item.label}: ${formatNumber(item.value)}`">
      <span class="label mono" :class="{ hot: props.highlight.includes(item.label) }">{{ item.label }}</span>
      <span class="track"><span class="fill" :class="{ hot: props.highlight.includes(item.label) }" :style="{ width: `${Math.max(0.6, (item.value / max) * 100)}%` }" /></span>
      <span class="value">{{ formatNumber(item.value) }}</span>
    </div>
  </div>
</template>

<style scoped>
.columns { display: flex; align-items: stretch; gap: 2px; border-bottom: 1px solid var(--axis); padding-bottom: 1.1rem; position: relative; }
.col { flex: 1; display: flex; flex-direction: column; justify-content: flex-end; position: relative; }
.col:hover .bar { background: #184f95; }
.bar { display: block; background: var(--laya); border-radius: 4px 4px 0 0; min-height: 1px; }
.tick { position: absolute; bottom: -1.1rem; left: 0; font-size: 0.55rem; color: var(--ink-muted); white-space: nowrap; }
.rows { display: grid; grid-template-columns: max-content 1fr 3rem; gap: 0.3rem 0.6rem; align-items: center; font-size: 0.72rem; }
.row { display: contents; }
.label { color: var(--ink-2); }
.label.hot { color: var(--critical); font-weight: 700; }
.track { height: 0.6rem; }
.fill { display: block; height: 100%; background: var(--laya); border-radius: 0 4px 4px 0; }
.fill.hot { background: var(--critical); }
.value { text-align: right; font-variant-numeric: tabular-nums; color: var(--ink-1); }
</style>
