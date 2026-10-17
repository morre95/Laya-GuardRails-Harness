<script setup lang="ts">
import { questions, type Answer } from '../data/demo'

const props = withDefaults(defineProps<{
  answers: Record<string, Answer>
  color?: string
  visible?: boolean
}>(), {
  color: 'var(--lgh-laya)',
  visible: true,
})

function label(key: string, answer: Answer): string {
  const question = questions.find(q => q.key === key)
  if (question?.type === 'noul')
    return `P(sant) ${answer.probability.toFixed(2)}`
  return `${answer.value} ${answer.probability.toFixed(2)}`
}
</script>

<template>
  <div class="answers">
    <div v-for="q in questions" :key="q.key" class="row">
      <div class="line">
        <span class="name">{{ q.key }}</span>
        <span class="value">{{ label(q.key, props.answers[q.key]) }}</span>
      </div>
      <div class="track">
        <div
          class="fill"
          :style="{
            width: props.visible ? `${props.answers[q.key].probability * 100}%` : '0%',
            background: props.color,
          }"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.answers {
  display: flex;
  flex-direction: column;
  gap: 7px;
}
.line {
  display: flex;
  justify-content: space-between;
  gap: 6px;
  margin-bottom: 2px;
}
.name {
  font-family: var(--slidev-code-font-family, monospace);
  font-size: 10.5px;
  color: var(--lgh-muted);
}
.value {
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
}
.track {
  height: 8px;
  background: var(--lgh-line);
  border-radius: 4px;
  overflow: hidden;
}
.fill {
  height: 100%;
  border-radius: 4px;
  transition: width 0.6s cubic-bezier(0.2, 0.8, 0.2, 1);
}
</style>
