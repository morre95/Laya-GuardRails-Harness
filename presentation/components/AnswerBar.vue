<script setup lang="ts">
import type { Answer } from '../data/demo'
import { chosenProbability, formatProbability } from '../data/demo'

const props = withDefaults(defineProps<{ answer: Answer, model?: 'laya' | 'base' }>(), { model: 'laya' })
const color = props.model === 'laya' ? 'var(--laya)' : 'var(--base)'
</script>

<template>
  <div class="answer">
    <template v-if="answer.type === 'noul'">
      <div class="track">
        <div class="fill" :style="{ width: `${answer.noul * 100}%`, background: color }" />
      </div>
      <div class="value"><span class="muted">P(sant)</span> {{ formatProbability(answer.noul) }}</div>
    </template>
    <template v-else>
      <div class="track split">
        <div
          v-for="(p, option) in answer.probabilities"
          :key="option"
          class="part"
          :style="{ flexGrow: p, background: option === answer.choice ? color : undefined }"
          :title="`${option} ${formatProbability(p)}`"
        />
      </div>
      <div class="value"><b>{{ answer.choice }}</b> {{ formatProbability(chosenProbability(answer)) }}</div>
    </template>
  </div>
</template>

<style scoped>
.answer {
  display: grid;
  grid-template-columns: 1fr 7rem;
  align-items: center;
  gap: 0.6rem;
}

.track {
  height: 0.75rem;
  background: var(--base-soft);
  border-radius: 999px;
  overflow: hidden;
  display: flex;
}

.fill {
  height: 100%;
  border-radius: 999px;
  transition: width 0.6s ease;
}

.split {
  gap: 2px;
  background: transparent;
}

.part {
  flex-basis: 0;
  background: var(--seg-pad);
  transition: flex-grow 0.6s ease, background 0.3s;
}

.value {
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
</style>
