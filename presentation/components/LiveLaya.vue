<script setup lang="ts">
import { onMounted, ref } from 'vue'
import type { Answers, LayaState } from '../data/demo'
import { formatCount, formatMs, presets, questions } from '../data/demo'

const TIMEOUT_MS = 3000

const presetLabels: Record<string, string> = {
  pytest: 'Kör testerna',
  checkout: 'Kasta lokala ändringar',
  curl: 'POST till extern tjänst',
  delete: 'DELETE i databasen',
}

interface Result {
  answers: Answers
  latencyMs: number
  inputTokens: number
  source: 'live' | 'inspelat'
}

const goal = ref(presets.delete.state.goal)
const command = ref(presets.delete.state.action.command ?? '')
const daemon = ref<'kontrollerar' | 'live' | 'nås inte'>('kontrollerar')
const model = ref('')
const running = ref(false)
const result = ref<Result | null>(null)
const error = ref('')
const history = ref<number[]>([])

async function request(path: string, init?: RequestInit) {
  const response = await fetch(`/laya${path}`, { ...init, signal: AbortSignal.timeout(TIMEOUT_MS) })
  if (!response.ok)
    throw new Error(`daemonen svarade ${response.status}`)
  return response.json()
}

onMounted(async () => {
  try {
    const health = await request('/health')
    daemon.value = health.ok ? 'live' : 'nås inte'
    model.value = String(health.model ?? '').split('/').pop() ?? ''
  }
  catch (exc) {
    console.warn('Laya daemon unreachable', exc)
    daemon.value = 'nås inte'
  }
})

function choosePreset(name: string) {
  goal.value = presets[name].state.goal
  command.value = presets[name].state.action.command ?? ''
}

function currentState(): LayaState {
  const base = presets.delete.state
  return { ...base, goal: goal.value, action: { ...base.action, command: command.value } }
}

function recordedResult(): Result | null {
  const match = Object.values(presets).find(p => p.state.goal === goal.value && p.state.action.command === command.value)
  if (!match)
    return null
  return {
    answers: match.fine_tuned.answers,
    latencyMs: match.fine_tuned.latency_ms,
    inputTokens: match.fine_tuned.input_tokens,
    source: 'inspelat',
  }
}

async function run() {
  running.value = true
  error.value = ''
  try {
    if (daemon.value !== 'live')
      throw new Error('daemonen nås inte')
    const body = await request('/predict', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ state: currentState(), questions }),
    })
    result.value = { answers: body.answers, latencyMs: body.latency_ms, inputTokens: body.usage.input_tokens, source: 'live' }
    history.value = [body.latency_ms, ...history.value].slice(0, 8)
  }
  catch (exc) {
    console.warn('Live Laya request failed', exc)
    result.value = recordedResult()
    if (!result.value)
      error.value = `${(exc as Error).message}. Välj en förinställning för att visa ett inspelat svar.`
  }
  finally {
    running.value = false
  }
}
</script>

<template>
  <div class="live">
    <div class="controls">
      <div class="presets">
        <button v-for="(label, name) in presetLabels" :key="name" class="preset" @click="choosePreset(name)">
          {{ label }}
        </button>
      </div>
      <label>mål<input v-model="goal" class="input"></label>
      <label>kommando<input v-model="command" class="input mono" @keydown.enter="run"></label>
      <div class="actions">
        <button class="run" :disabled="running" @click="run">{{ running ? 'Kör…' : 'Fråga Laya' }}</button>
        <span class="pill" :class="{ ok: daemon === 'live', warn: daemon === 'nås inte' }">
          daemon: {{ daemon }}<template v-if="model"> · {{ model }}</template>
        </span>
      </div>
      <div v-if="result" class="numbers">
        <div>
          <span class="stat" style="color: var(--laya)">{{ formatMs(result.latencyMs) }}</span>
          <div class="stat-label">
            {{ result.source === 'live' ? 'mätt i daemonen nu' : 'inspelat på RTX 3090' }}
          </div>
        </div>
        <div><span class="stat">{{ formatCount(result.inputTokens) }}</span><div class="stat-label">tokens in · 0 ut</div></div>
      </div>
      <div v-if="history.length" class="history">
        <span class="muted">senaste:</span>
        <span v-for="(ms, i) in history" :key="i" class="pill laya">{{ formatMs(ms) }}</span>
      </div>
      <div v-if="error" class="error">{{ error }}</div>
    </div>

    <div class="answers">
      <div class="answers-head">
        <span class="pill laya">finjusterad Laya</span>
        <span v-if="result?.source === 'inspelat'" class="pill warn">inspelat</span>
      </div>
      <ProbabilityBars v-if="result" :answers="result.answers" />
      <div v-else class="placeholder muted">Välj ett kommando och klicka på Fråga Laya</div>
    </div>
  </div>
</template>

<style scoped>
.live {
  display: grid;
  grid-template-columns: 1fr 1.25fr;
  gap: 1.5rem;
  font-size: 0.8rem;
}

.controls {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}

.presets {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
}

.preset {
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 0.15rem 0.7rem;
  background: var(--panel);
}

.preset:hover {
  border-color: var(--laya);
}

label {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
  color: var(--muted);
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.input {
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 0.35rem 0.55rem;
  font-size: 0.8rem;
  color: var(--ink);
  text-transform: none;
  letter-spacing: normal;
  background: var(--page);
}

.mono {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.72rem;
}

.actions {
  display: flex;
  align-items: center;
  gap: 0.8rem;
}

.run {
  background: var(--laya);
  color: white;
  font-weight: 600;
  border-radius: 8px;
  padding: 0.4rem 1rem;
}

.run:disabled {
  opacity: 0.6;
}

.numbers {
  display: grid;
  grid-template-columns: 1fr 1fr;
  margin-top: 0.4rem;
}

.history {
  display: flex;
  flex-wrap: wrap;
  gap: 0.3rem;
  align-items: center;
}

.error {
  color: var(--risk);
}

.answers {
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 0.9rem 1rem;
}

.answers-head {
  display: flex;
  gap: 0.4rem;
  margin-bottom: 0.7rem;
}

.placeholder {
  padding: 3rem 0;
  text-align: center;
}
</style>
