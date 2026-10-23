<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import LayaAnswers from './LayaAnswers.vue'
import { formatMs, formatNumber, recorded, SCENARIOS } from '../data'

const props = withDefaults(defineProps<{ initial?: string }>(), { initial: 'push' })

const scenario = ref(props.initial)
const elapsed = ref(0)
const running = ref(false)
let frame = 0
let startedAt = 0

const llm = computed(() => recorded.llm[scenario.value])
const laya = computed(() => recorded.laya.fine_tuned.states[scenario.value])
const state = computed(() => recorded.states[scenario.value] as { goal: string })

const llmText = computed(() => llm.value.chunks.filter(c => c.t_ms <= elapsed.value).map(c => c.text).join(''))
const llmTokens = computed(() => Math.round(llm.value.output_tokens * llmText.value.length / Math.max(1, llm.value.text.length)))
const llmDone = computed(() => elapsed.value >= llm.value.total_ms)
const layaDone = computed(() => elapsed.value >= laya.value.latency_ms)
const llmWaiting = computed(() => running.value && llmText.value.length === 0)
const ratio = computed(() => llm.value.total_ms / laya.value.latency_ms)

function tick(now: number) {
  elapsed.value = now - startedAt
  if (elapsed.value >= llm.value.total_ms) {
    elapsed.value = llm.value.total_ms
    running.value = false
    return
  }
  frame = requestAnimationFrame(tick)
}

function start() {
  cancelAnimationFrame(frame)
  elapsed.value = 0
  running.value = true
  startedAt = performance.now()
  frame = requestAnimationFrame(tick)
}

function choose(key: string) {
  cancelAnimationFrame(frame)
  scenario.value = key
  running.value = false
  elapsed.value = 0
}

onBeforeUnmount(() => cancelAnimationFrame(frame))
</script>

<template>
  <div class="race">
    <div class="controls">
      <button v-for="(command, key) in SCENARIOS" :key="key" class="btn mono" :class="{ active: key === scenario }" @click="choose(key)">
        {{ command }}
      </button>
      <button class="btn primary start" @click="start">{{ elapsed > 0 ? 'Kör igen' : 'Starta' }}</button>
    </div>
    <div class="goal muted">Mål: “{{ state.goal }}” · samma tillstånd och samma sju frågor till båda</div>

    <div class="panels">
      <div class="card panel">
        <div class="head">
          <span><span class="dot llm" />LLM <span class="muted small">({{ llm.model }} via claude -p)</span></span>
          <span class="clock mono">{{ formatMs(Math.min(elapsed, llm.total_ms)) }}</span>
        </div>
        <div class="meta muted">genererar text token för token · {{ llmTokens }} / {{ llm.output_tokens }} tokens</div>
        <pre class="stream mono"><span v-if="llmWaiting" class="muted">väntar på första token…</span>{{ llmText }}<span v-if="running" class="caret">▍</span></pre>
      </div>

      <div class="card panel">
        <div class="head">
          <span><span class="dot laya" />Laya <span class="muted small">(finjusterad, lokal GPU)</span></span>
          <span class="clock mono">{{ formatMs(Math.min(elapsed, laya.latency_ms)) }}</span>
        </div>
        <div class="meta muted">ett forward pass · {{ laya.input_tokens }} tokens in, {{ laya.output_tokens }} ut</div>
        <LayaAnswers v-if="layaDone" :answers="laya.answers" />
        <div v-else class="stream muted">{{ elapsed === 0 ? 'redo' : 'räknar…' }}</div>
      </div>
    </div>

    <div class="summary" :class="{ shown: llmDone }">
      Laya var klar efter <strong>{{ formatMs(laya.latency_ms) }}</strong>. LLM:en efter
      <strong>{{ formatMs(llm.total_ms) }}</strong>, alltså cirka <strong>{{ formatNumber(ratio) }} gånger</strong> långsammare.
    </div>
  </div>
</template>

<style scoped>
.race { display: grid; gap: 0.6rem; }
.controls { display: flex; flex-wrap: wrap; gap: 0.4rem; }
.start { margin-left: auto; }
.goal { font-size: 0.75rem; }
.panels { display: grid; grid-template-columns: 1fr 1fr; gap: 0.8rem; }
.panel { min-height: 15.5rem; display: grid; grid-template-rows: auto auto 1fr; gap: 0.4rem; }
.head { display: flex; justify-content: space-between; align-items: baseline; font-weight: 700; font-size: 0.9rem; color: var(--ink-1); }
.small { font-weight: 400; font-size: 0.7rem; }
.clock { font-size: 1.3rem; font-variant-numeric: tabular-nums; }
.meta { font-size: 0.7rem; }
.stream { margin: 0; font-size: 0.68rem; white-space: pre-wrap; word-break: break-word; color: var(--ink-1); background: var(--surface-2); border-radius: 6px; padding: 0.6rem; }
.caret { color: var(--llm); animation: blink 1s steps(1) infinite; }
@keyframes blink { 50% { opacity: 0; } }
.summary { font-size: 0.9rem; color: var(--ink-2); opacity: 0; transition: opacity 0.4s; }
.summary.shown { opacity: 1; }
</style>
