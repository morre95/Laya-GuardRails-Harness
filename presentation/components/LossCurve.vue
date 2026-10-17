<script setup lang="ts">
import { computed } from 'vue'

interface Epoch {
  epoch: number
  train_loss?: number
  val_loss: number
}

const props = defineProps<{ history: Epoch[] }>()

const WIDTH = 420
const HEIGHT = 230
const PAD = { left: 40, right: 20, top: 16, bottom: 34 }

const top = computed(() => Math.ceil(Math.max(...props.history.map(e => e.val_loss)) * 10) / 10)
const best = computed(() => props.history.reduce((a, b) => (b.val_loss < a.val_loss ? b : a)))
const last = computed(() => props.history[props.history.length - 1])
const ticks = computed(() => Array.from({ length: Math.round(top.value / 0.25) + 1 }, (_, i) => i * 0.25))

function x(epoch: number) {
  return PAD.left + (epoch / last.value.epoch) * (WIDTH - PAD.left - PAD.right)
}

function y(loss: number) {
  return PAD.top + (1 - loss / top.value) * (HEIGHT - PAD.top - PAD.bottom)
}

function line(points: [number, number][]) {
  return points.map(([e, l], i) => `${i ? 'L' : 'M'}${x(e)},${y(l)}`).join(' ')
}

const valPath = computed(() => line(props.history.map(e => [e.epoch, e.val_loss])))
const trainPath = computed(() => line(props.history.filter(e => e.train_loss !== undefined).map(e => [e.epoch, e.train_loss as number])))
</script>

<template>
  <svg :viewBox="`0 0 ${WIDTH} ${HEIGHT}`" class="curve">
    <g v-for="tick in ticks" :key="tick">
      <line :x1="PAD.left" :x2="WIDTH - PAD.right" :y1="y(tick)" :y2="y(tick)" class="grid" />
      <text :x="PAD.left - 6" :y="y(tick) + 3" text-anchor="end">{{ tick.toFixed(2).replace('.', ',') }}</text>
    </g>
    <text v-for="e in history" :key="e.epoch" :x="x(e.epoch)" :y="HEIGHT - 16" text-anchor="middle">{{ e.epoch }}</text>
    <text :x="(WIDTH + PAD.left) / 2" :y="HEIGHT - 2" text-anchor="middle">epok</text>
    <path :d="trainPath" class="train" />
    <path :d="valPath" class="val" />
    <circle v-for="e in history" :key="`v${e.epoch}`" :cx="x(e.epoch)" :cy="y(e.val_loss)" r="3.5" class="val-dot" />
    <circle :cx="x(best.epoch)" :cy="y(best.val_loss)" r="8" class="best" />
    <text :x="x(best.epoch) - 14" :y="y(best.val_loss) + 18" text-anchor="end" class="note">vikterna sparas</text>
    <text :x="x(last.epoch) - 4" :y="y(last.val_loss) - 12" text-anchor="end" class="note risk">stopp</text>
    <g class="legend">
      <line x1="250" x2="270" y1="24" y2="24" class="val" /><text x="275" y="27">validering</text>
      <line x1="250" x2="270" y1="40" y2="40" class="train" /><text x="275" y="43">träning</text>
    </g>
  </svg>
</template>

<style scoped>
.curve {
  width: 100%;
  font-size: 10px;
  fill: var(--muted);
}

.grid {
  stroke: var(--line);
}

.val {
  fill: none;
  stroke: var(--laya);
  stroke-width: 2.5;
}

.train {
  fill: none;
  stroke: var(--base);
  stroke-width: 2;
  stroke-dasharray: 5 4;
}

.val-dot {
  fill: var(--laya);
}

.best {
  fill: none;
  stroke: var(--ok);
  stroke-width: 2;
}

.note {
  fill: var(--ok);
  font-weight: 700;
}

.note.risk {
  fill: var(--risk);
}
</style>
