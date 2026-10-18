<script setup lang="ts">
import { computed } from 'vue'
import { formatNumber } from '../data'

const props = defineProps<{ history: { epoch: number, train_loss?: number, val_loss: number }[] }>()

const W = 520
const H = 230
const PAD = { left: 44, right: 90, top: 16, bottom: 34 }

const maxLoss = computed(() => Math.ceil(Math.max(...props.history.flatMap(h => [h.val_loss, h.train_loss ?? 0])) * 5) / 5)
const lastEpoch = computed(() => props.history[props.history.length - 1].epoch)
const x = (epoch: number) => PAD.left + (epoch / lastEpoch.value) * (W - PAD.left - PAD.right)
const y = (loss: number) => PAD.top + (1 - loss / maxLoss.value) * (H - PAD.top - PAD.bottom)

const train = computed(() => props.history.filter(h => h.train_loss !== undefined).map(h => ({ epoch: h.epoch, loss: h.train_loss as number })))
const val = computed(() => props.history.map(h => ({ epoch: h.epoch, loss: h.val_loss })))
const path = (points: { epoch: number, loss: number }[]) => points.map((p, i) => `${i ? 'L' : 'M'}${x(p.epoch)},${y(p.loss)}`).join(' ')
const best = computed(() => val.value.reduce((a, b) => (b.loss < a.loss ? b : a)))
const ticks = computed(() => Array.from({ length: Math.round(maxLoss.value / 0.2) + 1 }, (_, i) => i * 0.2))
</script>

<template>
  <svg :viewBox="`0 0 ${W} ${H}`" class="loss" role="img" aria-label="Träningsförlust och valideringsförlust per epok">
    <g v-for="tick in ticks" :key="tick">
      <line :x1="PAD.left" :x2="W - PAD.right" :y1="y(tick)" :y2="y(tick)" class="grid" />
      <text :x="PAD.left - 8" :y="y(tick) + 3" class="axis" text-anchor="end">{{ formatNumber(tick, 1) }}</text>
    </g>
    <text v-for="h in props.history" :key="h.epoch" :x="x(h.epoch)" :y="H - 12" class="axis" text-anchor="middle">epok {{ h.epoch }}</text>

    <path :d="path(train)" class="line train" />
    <path :d="path(val)" class="line val" />
    <g v-for="p in train" :key="`t${p.epoch}`"><circle :cx="x(p.epoch)" :cy="y(p.loss)" r="4" class="pt train"><title>träning, epok {{ p.epoch }}: {{ formatNumber(p.loss, 3) }}</title></circle></g>
    <g v-for="p in val" :key="`v${p.epoch}`"><circle :cx="x(p.epoch)" :cy="y(p.loss)" r="4" class="pt val"><title>validering, epok {{ p.epoch }}: {{ formatNumber(p.loss, 3) }}</title></circle></g>

    <circle :cx="x(best.epoch)" :cy="y(best.loss)" r="9" class="best" />
    <text :x="x(best.epoch) - 12" :y="y(best.loss) + 22" class="note" text-anchor="end">sparad: {{ formatNumber(best.loss, 2) }}</text>

    <text :x="W - PAD.right + 8" :y="y(val[val.length - 1].loss) + 4" class="label">validering</text>
    <text :x="W - PAD.right + 8" :y="y(train[train.length - 1].loss) + 4" class="label">träning</text>
  </svg>
</template>

<style scoped>
.loss { width: 100%; height: auto; }
.grid { stroke: var(--grid); stroke-width: 1; }
.axis { fill: var(--ink-muted); font-size: 10px; }
.line { fill: none; stroke-width: 2; }
.line.train { stroke: var(--base); stroke-dasharray: 5 4; }
.line.val { stroke: var(--laya); }
.pt { stroke: var(--surface-1); stroke-width: 2; }
.pt.train { fill: var(--base); }
.pt.val { fill: var(--laya); }
.best { fill: none; stroke: var(--ink-1); stroke-width: 1.5; }
.note { fill: var(--ink-1); font-size: 11px; font-weight: 700; }
.label { fill: var(--ink-2); font-size: 11px; }
</style>
