<script setup lang="ts">
import type { Answers } from '../data'
import { formatPercent, QUESTION_LABELS } from '../data'

const props = defineProps<{ answers: Answers }>()

function strength(key: string): number {
  const answer = props.answers[key]
  return answer.type === 'choice' ? answer.probabilities[answer.choice] : answer.noul
}

function valueText(key: string): string {
  const answer = props.answers[key]
  return answer.type === 'choice'
    ? `${answer.choice} ${formatPercent(answer.probabilities[answer.choice])}`
    : formatPercent(answer.noul)
}
</script>

<template>
  <div class="answers">
    <div v-for="key in Object.keys(QUESTION_LABELS)" :key="key" class="row">
      <span class="label">{{ QUESTION_LABELS[key] }}</span>
      <span class="track"><span class="fill" :style="{ width: `${strength(key) * 100}%` }" /></span>
      <span class="value">{{ valueText(key) }}</span>
    </div>
  </div>
</template>

<style scoped>
.answers { display: grid; gap: 0.3rem; }
.row { display: grid; grid-template-columns: 8.5rem 1fr 8rem; gap: 0.5rem; align-items: center; font-size: 0.72rem; }
.label { color: var(--ink-2); }
.track { height: 0.5rem; background: var(--surface-2); border-radius: 4px; overflow: hidden; }
.fill { display: block; height: 100%; background: var(--laya); border-radius: 0 4px 4px 0; }
.value { font-family: var(--mono); color: var(--ink-1); font-size: 0.68rem; text-align: right; }
</style>
