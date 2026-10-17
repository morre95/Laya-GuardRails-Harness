<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import type { Answers } from '../data/demo'
import { formatMs, questionKeys } from '../data/demo'

const props = defineProps<{
  running: boolean
  answers: Answers
  layaMs: number
}>()

// Illustration only: a generative model writing at 40 tokens/s.
const LLM_MS_PER_TOKEN = 25

const llmTokens = computed(() => {
  const fields = questionKeys.map((key) => {
    const answer = props.answers[key]
    const value = answer.type === 'noul' ? answer.noul.toFixed(2) : `"${answer.choice}"`
    return `"${key}": ${value}`
  })
  return `{${fields.join(', ')}}`.match(/[a-z]+|\d+|[^a-z\d\s]+|\s+/g) ?? []
})

const elapsed = ref(0)
let frame = 0

function tick(started: number) {
  elapsed.value = performance.now() - started
  if (elapsed.value < llmTokens.value.length * LLM_MS_PER_TOKEN + 200)
    frame = requestAnimationFrame(() => tick(started))
}

watch(() => props.running, (running) => {
  cancelAnimationFrame(frame)
  elapsed.value = 0
  if (running) {
    const started = performance.now()
    frame = requestAnimationFrame(() => tick(started))
  }
}, { immediate: true })

onBeforeUnmount(() => cancelAnimationFrame(frame))

const written = computed(() => Math.min(llmTokens.value.length, Math.floor(elapsed.value / LLM_MS_PER_TOKEN)))
const llmDone = computed(() => written.value === llmTokens.value.length)
const llmMs = computed(() => Math.min(elapsed.value, llmTokens.value.length * LLM_MS_PER_TOKEN))
const layaDone = computed(() => props.running && elapsed.value >= props.layaMs)
</script>

<template>
  <div class="race">
    <div class="lane">
      <div class="head">
        <span class="pill">Generativ språkmodell</span>
        <span class="muted">illustration: {{ 1000 / LLM_MS_PER_TOKEN }} tokens/s</span>
      </div>
      <pre class="output"><span v-for="(token, i) in llmTokens.slice(0, written)" :key="i" class="token">{{ token }}</span><span v-if="running && !llmDone" class="cursor">▍</span></pre>
      <div class="numbers">
        <div><span class="stat">{{ written }}</span><div class="stat-label">modellpass (ett per token)</div></div>
        <div><span class="stat">{{ formatMs(llmMs) }}</span><div class="stat-label">{{ llmDone ? 'klar' : 'skriver…' }}</div></div>
      </div>
    </div>

    <div class="lane laya">
      <div class="head">
        <span class="pill laya">Laya</span>
        <span class="muted">uppmätt</span>
      </div>
      <div class="output single" :class="{ done: layaDone }">
        <div class="pass-box">1 pass</div>
        <div class="arrow">→</div>
        <div class="answers">
          <div v-for="key in questionKeys" :key="key" class="answer-dot" />
          <span>7 fördelningar</span>
        </div>
      </div>
      <div class="numbers">
        <div><span class="stat" style="color: var(--laya)">{{ layaDone ? 1 : 0 }}</span><div class="stat-label">modellpass</div></div>
        <div><span class="stat" style="color: var(--laya)">{{ layaDone ? formatMs(layaMs) : '…' }}</span><div class="stat-label">{{ layaDone ? 'klar, 0 tokens ut' : '' }}</div></div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.race {
  display: grid;
  grid-template-columns: 1.35fr 1fr;
  gap: 1.5rem;
}

.lane {
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 0.9rem 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.8rem;
}

.lane.laya {
  border-color: var(--laya);
}

.head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 0.75rem;
}

.output {
  height: 9.5rem;
  margin: 0;
  padding: 0.7rem;
  background: var(--panel);
  border-radius: 8px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.72rem;
  white-space: pre-wrap;
  word-break: break-word;
  overflow: hidden;
}

.token:last-of-type {
  background: var(--seg-option-soft);
}

.cursor {
  color: var(--muted);
}

.single {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.8rem;
  opacity: 0.25;
  transition: opacity 0.2s;
}

.single.done {
  opacity: 1;
}

.pass-box {
  border: 2px solid var(--laya);
  border-radius: 8px;
  padding: 0.6rem 0.9rem;
  color: var(--laya);
  font-weight: 700;
}

.arrow {
  font-size: 1.4rem;
  color: var(--laya);
}

.answers {
  display: grid;
  grid-template-columns: repeat(7, 0.7rem);
  gap: 0.25rem;
  align-items: center;
}

.answers span {
  grid-column: 1 / -1;
  font-family: Inter, sans-serif;
  color: var(--muted);
  margin-top: 0.3rem;
}

.answer-dot {
  height: 1.6rem;
  border-radius: 3px;
  background: var(--laya);
}

.numbers {
  display: grid;
  grid-template-columns: 1fr 1fr;
}
</style>
