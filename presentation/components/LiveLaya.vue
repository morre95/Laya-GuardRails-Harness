<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import LayaAnswers from './LayaAnswers.vue'
import ProbabilityBars from './ProbabilityBars.vue'
import type { Answers } from '../data'
import { formatMs, recorded, SCENARIOS } from '../data'

interface DemoState {
  goal: string
  action: { command: string }
  [key: string]: unknown
}

const preset = ref('rm')
const goal = ref('')
const command = ref('')
const answers = ref<Answers | null>(null)
const source = ref<'live' | 'inspelat' | null>(null)
const serverMs = ref<number | null>(null)
const roundTripMs = ref<number | null>(null)
const daemonModel = ref<string | null>(null)
const error = ref<string | null>(null)
const busy = ref(false)

const presetState = computed(() => recorded.states[preset.value] as unknown as DemoState)
const edited = computed(() => goal.value !== presetState.value.goal || command.value !== presetState.value.action.command)
const handling = computed(() => answers.value?.handling)
const modelName = computed(() => (daemonModel.value ?? '').split('/').pop())

function choose(key: string) {
  preset.value = key
  goal.value = presetState.value.goal
  command.value = presetState.value.action.command
  answers.value = null
  error.value = null
}

function currentState(): DemoState {
  const state = structuredClone(presetState.value)
  state.goal = goal.value
  state.action = { ...state.action, command: command.value }
  return state
}

async function checkHealth() {
  try {
    const response = await fetch('/laya/health')
    const health = await response.json()
    daemonModel.value = health.ok ? health.model : null
  }
  catch (exc) {
    console.error('Laya daemon health check failed', exc)
    daemonModel.value = null
  }
}

function useRecording(reason: string) {
  if (edited.value) {
    answers.value = null
    error.value = `${reason} Bara de förinställda kommandona finns inspelade.`
    return
  }
  const run = recorded.laya.fine_tuned.states[preset.value]
  answers.value = run.answers
  serverMs.value = run.latency_ms
  roundTripMs.value = null
  source.value = 'inspelat'
}

async function run() {
  busy.value = true
  error.value = null
  const started = performance.now()
  try {
    const response = await fetch('/laya/predict', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ state: currentState(), questions: recorded.questions }),
    })
    if (!response.ok)
      throw new Error(`daemonen svarade ${response.status}`)
    const body = await response.json()
    roundTripMs.value = performance.now() - started
    serverMs.value = body.latency_ms
    answers.value = body.answers
    daemonModel.value = body.model
    source.value = 'live'
  }
  catch (exc) {
    console.error('Live Laya request failed', exc)
    useRecording('Laya-daemonen svarar inte.')
  }
  finally {
    busy.value = false
  }
}

onMounted(() => {
  choose(preset.value)
  checkHealth()
})
</script>

<template>
  <div class="live">
    <div class="card inputs">
      <div class="presets">
        <button v-for="(text, key) in SCENARIOS" :key="key" class="btn mono" :class="{ active: key === preset && !edited }" @click="choose(key)">{{ text }}</button>
      </div>
      <label class="field">
        <span class="kicker">Användarens mål</span>
        <input v-model="goal" class="input">
      </label>
      <label class="field">
        <span class="kicker">Kommando agenten vill köra</span>
        <input v-model="command" class="input mono" @keydown.enter="run">
      </label>
      <button class="btn primary" :disabled="busy" @click="run">{{ busy ? 'Frågar Laya…' : 'Fråga Laya' }}</button>
      <div class="status muted">
        <span v-if="daemonModel"><span class="dot laya" />daemonen kör {{ modelName }}</span>
        <span v-else>daemonen nås inte, inspelade svar används</span>
      </div>
    </div>

    <div class="card result">
      <template v-if="answers">
        <div class="head">
          <span class="tag" :class="{ laya: source === 'live' }">{{ source }}</span>
          <span class="mono timing">{{ formatMs(serverMs ?? 0) }} i modellen<template v-if="roundTripMs"> · {{ formatMs(roundTripMs) }} totalt via HTTP</template></span>
        </div>
        <LayaAnswers :answers="answers" />
        <div v-if="handling && handling.type === 'choice'" class="detail">
          <div class="kicker">Hantering, hela fördelningen</div>
          <ProbabilityBars :probabilities="handling.probabilities" :chosen="handling.choice" />
        </div>
      </template>
      <p v-else-if="error" class="error">{{ error }}</p>
      <p v-else class="muted">Välj ett kommando eller skriv ett eget och tryck på <strong>Fråga Laya</strong>.</p>
    </div>
  </div>
</template>

<style scoped>
.live { display: grid; grid-template-columns: 0.9fr 1.1fr; gap: 0.8rem; }
.inputs { display: grid; gap: 0.6rem; align-content: start; }
.presets { display: flex; flex-wrap: wrap; gap: 0.35rem; }
.field { display: grid; gap: 0.2rem; }
.input { font-size: 0.8rem; padding: 0.35rem 0.5rem; border: 1px solid var(--axis); border-radius: 6px; background: var(--surface-1); color: var(--ink-1); }
.status { font-size: 0.7rem; }
.result { display: grid; gap: 0.6rem; align-content: start; min-height: 17rem; }
.head { display: flex; justify-content: space-between; align-items: center; }
.timing { font-size: 0.75rem; color: var(--ink-1); }
.detail { display: grid; gap: 0.3rem; }
.error { color: var(--critical) !important; font-size: 0.8rem; }
</style>
