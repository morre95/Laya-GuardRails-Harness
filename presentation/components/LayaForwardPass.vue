<script setup lang="ts">
import { computed } from 'vue'
import type { Answers, SequenceLayout } from '../data/demo'
import { formatCount, formatMs, metrics, questionKeys, questionLabels } from '../data/demo'

const props = defineProps<{
  step: number
  layout: Record<string, SequenceLayout>
  answers: Answers
  latencyMs: number
  inputTokens: number
}>()

const longest = computed(() => Math.max(...questionKeys.map(key => props.layout[key].tokens)))

function percent(tokens: number): string {
  return `${(tokens / longest.value) * 100}%`
}

function segments(key: string) {
  const row = props.layout[key]
  const head = row.marker_positions[0]
  return { head, options: row.options, state: row.tokens - head - row.options }
}

const captions = computed(() => [
  'Sju frågor om samma tillstånd',
  'Varje fråga blir en egen sekvens: frågan, en [MASK] per svar, sedan tillståndet',
  `Alla sju läggs i en batch: ${questionKeys.length} rader × ${longest.value} tokens`,
  'Ett enda pass genom encodern, alla rader samtidigt och åt båda hållen',
  'Svaret läses direkt vid [MASK]-positionerna, alla sju på en gång',
  'Klart',
])
</script>

<template>
  <div class="pass">
    <div class="caption">
      <span class="step">{{ Math.min(step, 5) + 1 }}/6</span>
      {{ captions[Math.min(step, 5)] }}
    </div>

    <div class="grid">
      <div class="legend" :class="{ shown: step >= 1 }">
        <span><i style="background: var(--seg-head)" /> fråga</span>
        <span><i style="background: var(--seg-option)" /> svarsalternativ</span>
        <span><i class="mask" /> [MASK]</span>
        <span><i style="background: var(--seg-state)" /> tillstånd (samma i alla)</span>
        <span v-if="step >= 2"><i style="background: var(--seg-pad)" /> utfyllnad</span>
      </div>

      <template v-for="(key, index) in questionKeys" :key="key">
        <div class="label">
          <span class="key">{{ key }}</span>
          <span class="question">{{ questionLabels[key] }}</span>
        </div>

        <div class="lane" :class="{ batched: step >= 2 }">
          <div
            class="strip"
            :class="{ built: step >= 1 }"
            :style="{ width: percent(layout[key].tokens), transitionDelay: `${index * 90}ms` }"
          >
            <div class="seg" :style="{ flexGrow: segments(key).head, background: 'var(--seg-head)' }" />
            <div class="seg" :style="{ flexGrow: segments(key).options, background: 'var(--seg-option)' }" />
            <div class="seg" :style="{ flexGrow: segments(key).state, background: 'var(--seg-state)' }" />
            <div
              v-for="marker in layout[key].marker_positions"
              :key="marker"
              class="marker"
              :class="{ lit: step >= 4 }"
              :style="{ left: `${(marker / layout[key].tokens) * 100}%` }"
            />
          </div>
          <div class="tokens" :class="{ shown: step >= 1 }">{{ layout[key].tokens }}</div>
        </div>

        <div class="out" :class="{ shown: step >= 4 }">
          <AnswerBar :answer="answers[key]" />
        </div>
      </template>

      <div class="encoder" :class="{ shown: step >= 3 }">
        <div v-if="step === 3" class="sweep" />
        <span>ModernBERT-large + typat beslutshuvud · ett pass</span>
      </div>
      <div class="batch" :class="{ shown: step >= 2 }">batch</div>
    </div>

    <div class="result" :class="{ shown: step >= 5 }">
      <div><span class="stat" style="color: var(--laya)">{{ formatMs(latencyMs) }}</span><div class="stat-label">ett pass på RTX 3090</div></div>
      <div><span class="stat">{{ formatCount(inputTokens) }}</span><div class="stat-label">tokens in (7 sekvenser)</div></div>
      <div><span class="stat">0</span><div class="stat-label">tokens ut</div></div>
      <div><span class="stat">{{ formatMs(metrics.traces.latency_ms.p50) }}</span><div class="stat-label">median i {{ formatCount(metrics.traces.assessments) }} riktiga bedömningar</div></div>
    </div>
  </div>
</template>

<style scoped>
.pass {
  font-size: 0.78rem;
}

.caption {
  font-size: 1rem;
  font-weight: 600;
  margin-bottom: 0.6rem;
  min-height: 1.5rem;
}

.step {
  display: inline-block;
  font-size: 0.75rem;
  color: var(--laya);
  background: var(--laya-soft);
  border-radius: 999px;
  padding: 0 0.5rem;
  margin-right: 0.4rem;
}

.grid {
  position: relative;
  display: grid;
  grid-template-columns: 12.5rem 1fr 15rem;
  column-gap: 1rem;
  row-gap: 0.32rem;
  align-items: center;
}

.legend {
  grid-column: 2 / 4;
  display: flex;
  gap: 1rem;
  color: var(--muted);
  font-size: 0.7rem;
  opacity: 0;
  transition: opacity 0.4s;
}

.legend.shown {
  opacity: 1;
}

.legend i {
  display: inline-block;
  width: 0.7rem;
  height: 0.7rem;
  border-radius: 2px;
  vertical-align: -1px;
}

.legend i.mask {
  width: 3px;
  background: var(--ink);
}

.label {
  grid-column: 1;
  display: flex;
  flex-direction: column;
  line-height: 1.15;
}

.key {
  font-family: 'JetBrains Mono', monospace;
}

.question {
  color: var(--muted);
  font-size: 0.9em;
}

.lane {
  grid-column: 2;
  position: relative;
  display: flex;
  align-items: center;
  gap: 0.4rem;
  height: 1.55rem;
  border: 1px dashed var(--line);
  border-radius: 4px;
  padding: 0 2.2rem 0 0;
  transition: background 0.4s;
}

.lane.batched {
  background: var(--seg-pad);
  border-style: solid;
}

.strip {
  position: relative;
  height: 100%;
  display: flex;
  border-radius: 3px;
  overflow: visible;
  transform: scaleX(0);
  transform-origin: left;
  transition: transform 0.6s ease;
}

.strip.built {
  transform: scaleX(1);
}

.seg {
  flex-basis: 0;
  height: 100%;
}

.marker {
  position: absolute;
  top: -3px;
  bottom: -3px;
  width: 3px;
  background: var(--ink);
  border-radius: 2px;
  transition: box-shadow 0.4s, background 0.4s;
}

.marker.lit {
  background: var(--laya);
  box-shadow: 0 0 0 3px var(--laya-soft), 0 0 10px var(--laya);
}

.tokens {
  position: absolute;
  right: 0.3rem;
  color: var(--muted);
  font-variant-numeric: tabular-nums;
  opacity: 0;
  transition: opacity 0.4s 0.6s;
}

.tokens.shown {
  opacity: 1;
}

.out {
  grid-column: 3;
  opacity: 0;
  transform: translateX(-12px);
  transition: opacity 0.5s, transform 0.5s;
}

.out.shown {
  opacity: 1;
  transform: none;
}

.encoder {
  position: absolute;
  top: 1.4rem;
  bottom: -0.2rem;
  left: calc(12.5rem + 0.5rem);
  right: calc(15rem + 0.5rem);
  border: 2px solid var(--laya);
  border-radius: 8px;
  background: rgba(109, 63, 214, 0.08);
  overflow: hidden;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.4s;
}

.encoder.shown {
  opacity: 1;
}

.encoder span {
  position: absolute;
  bottom: 0.2rem;
  right: 0.5rem;
  font-size: 0.68rem;
  font-weight: 600;
  color: var(--laya);
  background: var(--page);
  padding: 0 0.35rem;
  border-radius: 4px;
}

.sweep {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 30%;
  background: linear-gradient(90deg, transparent, rgba(109, 63, 214, 0.45), transparent);
  animation: sweep 1.1s ease-in-out 1 forwards;
}

@keyframes sweep {
  from { left: -30%; }
  to { left: 100%; }
}

.batch {
  position: absolute;
  top: 1.6rem;
  bottom: 0;
  left: 12.85rem;
  width: 0.5rem;
  border: 2px solid var(--ink);
  border-right: none;
  border-radius: 4px 0 0 4px;
  font-size: 0;
  opacity: 0;
  transition: opacity 0.4s;
}

.batch.shown {
  opacity: 1;
}

.result {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 1rem;
  margin-top: 1rem;
  opacity: 0;
  transform: translateY(8px);
  transition: opacity 0.5s, transform 0.5s;
}

.result.shown {
  opacity: 1;
  transform: none;
}
</style>
