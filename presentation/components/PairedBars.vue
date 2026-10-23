<script setup lang="ts">
import { computed } from 'vue'
import { formatNumber, formatPercent } from '../data'

interface Row { label: string, base: number, tuned: number, baseline?: number }

const props = withDefaults(defineProps<{
  rows: Row[]
  percent?: boolean
  baselineLabel?: string
}>(), { percent: true, baselineLabel: 'gissa alltid vanligaste klassen' })

const max = computed(() => props.percent ? 1 : Math.max(...props.rows.flatMap(row => [row.base, row.tuned])))
const format = (value: number) => props.percent ? formatPercent(value) : formatNumber(value, 2)
const width = (value: number) => `${(value / max.value) * 100}%`
const hasBaseline = computed(() => props.rows.some(row => row.baseline !== undefined))
</script>

<template>
  <div class="paired">
    <div class="legend muted">
      <span><span class="dot base" />grundmodell</span>
      <span><span class="dot laya" />finjusterad</span>
      <span v-if="hasBaseline"><i class="tickmark" />{{ props.baselineLabel }}</span>
    </div>
    <div v-for="row in props.rows" :key="row.label" class="row">
      <span class="label">{{ row.label }}</span>
      <div class="bars">
        <div class="bar-line" :title="`grundmodell: ${format(row.base)}`">
          <span class="fill base" :style="{ width: width(row.base) }" /><span class="value">{{ format(row.base) }}</span>
        </div>
        <div class="bar-line" :title="`finjusterad: ${format(row.tuned)}`">
          <span class="fill tuned" :style="{ width: width(row.tuned) }" /><span class="value strong">{{ format(row.tuned) }}</span>
        </div>
        <span v-if="row.baseline !== undefined" class="baseline" :style="{ left: width(row.baseline) }" :title="`${props.baselineLabel}: ${format(row.baseline)}`" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.paired { display: grid; gap: 0.45rem; }
.legend { display: flex; gap: 1.2rem; font-size: 0.68rem; }
.tickmark { display: inline-block; width: 0; height: 0.8rem; border-left: 2px dashed var(--ink-1); margin-right: 0.35rem; vertical-align: middle; }
.row { display: grid; grid-template-columns: 9rem 1fr; gap: 0.6rem; align-items: center; }
.label { font-size: 0.75rem; color: var(--ink-2); }
.bars { position: relative; display: grid; gap: 2px; margin-right: 3rem; }
.bar-line { display: flex; align-items: center; gap: 0.35rem; height: 0.7rem; }
.fill { display: block; height: 100%; border-radius: 0 4px 4px 0; flex: none; }
.fill.base { background: var(--base); }
.fill.tuned { background: var(--laya); }
.value { font-size: 0.62rem; color: var(--ink-2); font-variant-numeric: tabular-nums; white-space: nowrap; }
.value.strong { color: var(--ink-1); font-weight: 700; }
.baseline { position: absolute; top: -2px; bottom: -2px; border-left: 2px dashed var(--ink-1); }
</style>
