<script setup lang="ts">
import { formatPercent } from '../data'

const props = defineProps<{
  probabilities: Record<string, number>
  chosen?: string
  compact?: boolean
}>()
</script>

<template>
  <div class="probs" :class="{ compact: props.compact }">
    <div v-for="(p, option) in props.probabilities" :key="option" class="row" :title="`${option}: ${formatPercent(p)}`">
      <span class="label" :class="{ chosen: option === props.chosen }">{{ option }}</span>
      <span class="track"><span class="fill" :class="{ chosen: option === props.chosen }" :style="{ width: `${p * 100}%` }" /></span>
      <span class="value">{{ formatPercent(p) }}</span>
    </div>
  </div>
</template>

<style scoped>
.probs { display: grid; gap: 0.25rem; }
.row { display: grid; grid-template-columns: 7rem 1fr 3rem; align-items: center; gap: 0.5rem; font-size: 0.75rem; }
.compact .row { grid-template-columns: 6rem 1fr 2.6rem; font-size: 0.65rem; gap: 0.35rem; }
.label { color: var(--ink-2); font-family: var(--mono); }
.label.chosen { color: var(--ink-1); font-weight: 700; }
.track { height: 0.55rem; background: var(--surface-2); border-radius: 4px; overflow: hidden; }
.fill { display: block; height: 100%; background: var(--laya-soft); border-radius: 0 4px 4px 0; transition: width 0.4s ease; }
.fill.chosen { background: var(--laya); }
.value { text-align: right; color: var(--ink-2); font-variant-numeric: tabular-nums; }
</style>
