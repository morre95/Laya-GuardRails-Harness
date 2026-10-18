<script setup lang="ts">
import { computed } from 'vue'
import ProbabilityBars from './ProbabilityBars.vue'
import { formatMs, formatNumber, recorded } from '../data'

const props = withDefaults(defineProps<{ step?: number }>(), { step: 0 })

const SHOWN_STATE_TOKENS = 14
const layout = recorded.laya.fine_tuned.handling_layout
const run = recorded.laya.fine_tuned.states.rm
const handling = run.answers.handling
const parameters = recorded.laya.fine_tuned.parameters

type Segment = 'special' | 'head' | 'mask' | 'option' | 'state'

const tokens = computed(() => {
  const seps = layout.flatMap((token, index) => (token === '[SEP]' ? [index] : []))
  return layout.map((token, index) => {
    let segment: Segment = 'state'
    if (token === '[CLS]' || token === '[SEP]') segment = 'special'
    else if (token === '[MASK]') segment = 'mask'
    else if (index < seps[0]) segment = 'head'
    else if (index < seps[1]) segment = 'option'
    return { text: token.replace(/Ġ/g, '').replace(/Ċ/g, '↵'), segment, index }
  })
})

const stateStart = computed(() => layout.indexOf('[SEP]', layout.indexOf('[SEP]') + 1) + 1)
const visible = computed(() => tokens.value.slice(0, stateStart.value + SHOWN_STATE_TOKENS))
const hiddenCount = computed(() => layout.length - visible.value.length)
const options = Object.keys(handling.type === 'choice' ? handling.probabilities : {})
</script>

<template>
  <div class="pass">
    <div class="sequence">
      <span v-for="token in visible" :key="token.index" class="tok mono" :class="token.segment">{{ token.text }}</span>
      <span class="tok more mono">… +{{ hiddenCount }} tokens</span>
    </div>
    <div class="legend muted">
      <span><i class="sw head" />fråga</span>
      <span><i class="sw mask" />[MASK] = ett svarsalternativ</span>
      <span><i class="sw option" />alternativets text</span>
      <span><i class="sw state" />agentens tillstånd (JSON)</span>
    </div>

    <div class="flow">
      <div class="card stage" :class="{ hidden: props.step < 1 }">
        <div class="kicker">1 · Encoder</div>
        <h3>ModernBERT-large</h3>
        <p>{{ formatNumber(parameters / 1e6) }} M parametrar. Alla {{ layout.length }} tokens läses <strong>samtidigt</strong>, åt båda hållen.
          Sju sådana sekvenser, en per fråga, körs i <strong>en batch</strong>.</p>
      </div>
      <div class="card stage" :class="{ hidden: props.step < 2 }">
        <div class="kicker">2 · Avläsning</div>
        <h3>En poäng per [MASK]</h3>
        <div class="masks">
          <span v-for="option in options" :key="option" class="mask-chip mono">[MASK] → {{ option }}</span>
        </div>
        <p>Beslutshuvudet läser vektorn på varje markör. Inget svar skrivs ut.</p>
      </div>
      <div class="card stage" :class="{ hidden: props.step < 3 }">
        <div class="kicker">3 · Sannolikheter</div>
        <h3>Softmax med temperatur</h3>
        <ProbabilityBars v-if="handling.type === 'choice'" :probabilities="handling.probabilities" :chosen="handling.choice" compact />
        <p class="muted">Alla sju frågor: {{ formatMs(run.latency_ms) }}, 0 output-tokens.</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.pass { display: grid; gap: 0.7rem; }
.sequence { display: flex; flex-wrap: wrap; gap: 0.18rem; }
.tok { font-size: 0.58rem; padding: 0.05rem 0.25rem; border-radius: 3px; background: var(--surface-2); color: var(--ink-2); }
.tok.special { background: var(--ink-1); color: var(--surface-1); }
.tok.head { background: var(--surface-2); color: var(--ink-1); }
.tok.mask { background: var(--laya); color: #fff; font-weight: 700; }
.tok.option { background: var(--laya-soft); color: #184f95; }
.tok.state { background: transparent; border: 1px solid var(--grid); }
.tok.more { background: transparent; color: var(--ink-muted); }
.legend { display: flex; gap: 1rem; font-size: 0.65rem; }
.sw { display: inline-block; width: 0.6rem; height: 0.6rem; border-radius: 2px; margin-right: 0.3rem; vertical-align: middle; }
.sw.head { background: var(--surface-2); border: 1px solid var(--axis); }
.sw.mask { background: var(--laya); }
.sw.option { background: var(--laya-soft); }
.sw.state { border: 1px solid var(--axis); }
.flow { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.7rem; }
.stage { transition: opacity 0.4s; display: grid; align-content: start; gap: 0.35rem; }
.stage.hidden { opacity: 0; }
.stage p { margin: 0; font-size: 0.72rem; }
.masks { display: grid; gap: 0.2rem; }
.mask-chip { font-size: 0.65rem; color: #184f95; background: var(--laya-soft); border-radius: 4px; padding: 0.1rem 0.4rem; }
</style>
