<script setup lang="ts">
import type { Answers } from '../data/demo'
import { questionKeys, questionLabels } from '../data/demo'

withDefaults(defineProps<{
  answers: Answers
  model?: 'laya' | 'base'
  compact?: boolean
}>(), { model: 'laya', compact: false })
</script>

<template>
  <div class="bars" :class="{ compact }">
    <div v-for="key in questionKeys" :key="key" class="row">
      <div class="label">
        <span class="key">{{ key }}</span>
        <span v-if="!compact" class="question">{{ questionLabels[key] }}</span>
      </div>
      <AnswerBar :answer="answers[key]" :model="model" />
    </div>
  </div>
</template>

<style scoped>
.bars {
  display: grid;
  gap: 0.45rem;
  font-size: 0.8rem;
}

.compact {
  gap: 0.3rem;
  font-size: 0.72rem;
}

.row {
  display: grid;
  grid-template-columns: 13rem 1fr;
  align-items: center;
  gap: 0.6rem;
}

.compact .row {
  grid-template-columns: 9.5rem 1fr;
}

.label {
  display: flex;
  flex-direction: column;
  line-height: 1.15;
}

.key {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.92em;
}

.question {
  color: var(--muted);
  font-size: 0.85em;
}
</style>
