<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { demoRun, questions } from '../data/demo'

const props = defineProps<{ running: boolean }>()

// Illustration, inte mätning: typisk LLM-takt med väntan innan första token.
const LLM_FIRST_TOKEN_MS = 800
const LLM_CHARS_PER_SECOND = 200
const LLM_OUTPUT = `{"task_alignment": "supporting", "destructive_risk": 0.22, "sensitive_resource": 0.23, "external_impact": 0.10, "reversibility": "trivial", "verification_needed": 0.29, "handling": "allow", "reason": "The command deletes rows from the users table, which is not obviously part of fixing the test..."}`
const LLM_TOTAL_MS = LLM_FIRST_TOKEN_MS + (LLM_OUTPUT.length / LLM_CHARS_PER_SECOND) * 1000

const elapsed = ref(0)
let frame = 0
let startedAt = 0

function tick(now: number) {
  elapsed.value = now - startedAt
  if (elapsed.value < LLM_TOTAL_MS)
    frame = requestAnimationFrame(tick)
  else
    elapsed.value = LLM_TOTAL_MS
}

watch(
  () => props.running,
  (running) => {
    cancelAnimationFrame(frame)
    elapsed.value = 0
    if (running) {
      startedAt = performance.now()
      frame = requestAnimationFrame(tick)
    }
  },
  { immediate: true },
)

onBeforeUnmount(() => cancelAnimationFrame(frame))

const layaDone = computed(() => elapsed.value >= demoRun.latencyMs)
const layaClock = computed(() => Math.min(elapsed.value, demoRun.latencyMs))
const llmText = computed(() => {
  const typing = Math.max(0, elapsed.value - LLM_FIRST_TOKEN_MS)
  return LLM_OUTPUT.slice(0, Math.floor((typing / 1000) * LLM_CHARS_PER_SECOND))
})
const llmDone = computed(() => elapsed.value >= LLM_TOTAL_MS)
</script>

<template>
  <div class="race">
    <div class="lane">
      <div class="head">
        <span class="lgh-pill laya">Laya</span>
        <span>klassificerar · ett pass</span>
        <span class="clock laya">{{ layaClock.toFixed(0) }} ms</span>
      </div>
      <div class="body chips">
        <span
          v-for="q in questions"
          :key="q.key"
          class="chip"
          :class="{ on: layaDone }"
        >{{ q.key }}</span>
      </div>
    </div>

    <div class="lane">
      <div class="head">
        <span class="lgh-pill">LLM</span>
        <span>genererar · token för token</span>
        <span class="clock">{{ (elapsed / 1000).toFixed(2) }} s</span>
      </div>
      <div class="body mono">
        <span v-if="props.running && !llmText" class="lgh-muted">väntar på första token…</span>
        {{ llmText }}<span v-if="props.running && !llmDone" class="caret">▍</span>
      </div>
    </div>
    <p class="note lgh-muted">
      Laya-tiden är uppmätt. LLM-raden är en illustration av autoregressiv generering
      (≈ 50 tokens/s), inte en mätning.
    </p>
  </div>
</template>

<style scoped>
.race {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.lane {
  border: 1px solid var(--lgh-line);
  border-radius: 10px;
  overflow: hidden;
}
.head {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 12px;
  background: var(--lgh-panel);
  font-size: 13px;
}
.clock {
  margin-left: auto;
  font-family: var(--slidev-code-font-family, monospace);
  font-weight: 700;
  font-size: 18px;
}
.clock.laya {
  color: var(--lgh-laya);
}
.body {
  min-height: 64px;
  padding: 10px 12px;
  font-size: 12px;
}
.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-content: center;
}
.chip {
  font-family: var(--slidev-code-font-family, monospace);
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 999px;
  border: 1px solid var(--lgh-line);
  color: var(--lgh-muted);
}
.chip.on {
  background: var(--lgh-laya);
  border-color: var(--lgh-laya);
  color: white;
}
.mono {
  font-family: var(--slidev-code-font-family, monospace);
  font-size: 11px;
  word-break: break-all;
}
.caret {
  animation: blink 0.8s steps(1) infinite;
}
@keyframes blink {
  50% {
    opacity: 0;
  }
}
.note {
  font-size: 11px;
  margin: 0 !important;
}
</style>
