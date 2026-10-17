<script setup lang="ts">
import { demoRun, demoState, fineTunedAnswers, questions } from '../data/demo'

// step 0: tillståndet · 1: sju sekvenser · 2: ett forward pass · 3: svaren · 4: siffrorna
const props = defineProps<{ step: number }>()
</script>

<template>
  <div class="stage">
    <section class="col">
      <h4>Agentens tillstånd</h4>
      <div class="state">
        <div><b>goal</b> {{ demoState.goal }}</div>
        <div><b>plan</b> {{ demoState.plan }}</div>
        <div><b>repo</b> {{ demoState.repo }}</div>
        <div><b>env</b> {{ demoState.environment }}</div>
        <div class="command">
          <b>{{ demoState.tool }}</b> {{ demoState.command }}
        </div>
      </div>
    </section>

    <section class="col middle" :class="{ hidden: props.step < 1 }">
      <h4>
        Sju frågor · samma tillstånd
        <span class="lgh-muted">→ en batch</span>
      </h4>
      <div class="batch" :class="{ encoding: props.step === 2, encoded: props.step >= 2 }">
        <div
          v-for="(q, i) in questions"
          :key="q.key"
          class="seq"
          :style="{ transitionDelay: `${i * 70}ms` }"
        >
          <span class="tok special">CLS</span>
          <span class="tok type" :class="q.type">{{ q.type }}</span>
          <span class="tok text">{{ q.label }}</span>
          <span class="tok special">SEP</span>
          <span v-for="n in q.options" :key="n" class="tok mask">M</span>
          <span class="tok special">SEP</span>
          <span class="tok state">tillstånd…</span>
        </div>
        <div class="encoder" :class="{ hidden: props.step < 2 }">
          ModernBERT-large · 28 lager · ett enda forward pass för alla sju rader
        </div>
      </div>
      <p class="hint lgh-muted" :class="{ hidden: props.step < 2 }">
        Svaret läses av där <span class="tok mask inline">M</span> står, en markör per svarsalternativ.
        Ingen text genereras.
      </p>
    </section>

    <section class="col" :class="{ hidden: props.step < 3 }">
      <h4>Sju svar · samtidigt</h4>
      <AnswerBars :answers="fineTunedAnswers" :visible="props.step >= 3" />
    </section>

    <div class="stats" :class="{ hidden: props.step < 4 }">
      <div><span class="lgh-big">1</span><br>forward pass</div>
      <div><span class="lgh-big">{{ demoRun.inputTokens }}</span><br>tokens in</div>
      <div><span class="lgh-big">{{ demoRun.outputTokens }}</span><br>tokens ut</div>
      <div><span class="lgh-big">≈{{ demoRun.latencyMs }} ms</span><br>RTX 3090</div>
    </div>
  </div>
</template>

<style scoped>
.stage {
  display: grid;
  grid-template-columns: 210px 1fr 190px;
  grid-template-rows: auto auto;
  gap: 14px 18px;
  font-size: 12px;
}
.col {
  transition: opacity 0.5s ease, transform 0.5s ease;
}
.hidden {
  opacity: 0;
  transform: translateY(8px);
  pointer-events: none;
}
h4 {
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-bottom: 6px;
}
.state {
  background: var(--lgh-panel);
  border: 1px solid var(--lgh-line);
  border-radius: 8px;
  padding: 8px 10px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 11px;
  line-height: 1.35;
}
.state b {
  font-family: var(--slidev-code-font-family, monospace);
  color: var(--lgh-accent);
  margin-right: 4px;
}
.command {
  font-family: var(--slidev-code-font-family, monospace);
  background: #fbe7e5;
  border-radius: 6px;
  padding: 4px 6px;
  color: var(--lgh-risk);
  word-break: break-all;
}
.batch {
  position: relative;
  border: 2px dashed var(--lgh-line);
  border-radius: 10px;
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 5px;
  transition: border-color 0.4s ease, background 0.4s ease;
}
.batch.encoded {
  border: 2px solid var(--lgh-laya);
  background: var(--lgh-laya-soft);
}
.seq {
  display: flex;
  gap: 3px;
  align-items: center;
  white-space: nowrap;
  overflow: hidden;
}
.tok {
  font-family: var(--slidev-code-font-family, monospace);
  font-size: 9.5px;
  border-radius: 4px;
  padding: 1px 4px;
  background: white;
  border: 1px solid var(--lgh-line);
  transition: background 0.4s ease, color 0.4s ease;
}
.tok.special {
  color: var(--lgh-muted);
}
.tok.type.noul {
  color: var(--lgh-accent);
}
.tok.type.choice {
  color: var(--lgh-warn);
}
.tok.text {
  font-family: inherit;
  font-size: 10.5px;
  flex: 0 1 auto;
  overflow: hidden;
  text-overflow: ellipsis;
}
.tok.mask {
  font-weight: 700;
}
.encoded .tok.mask,
.tok.mask.inline {
  background: var(--lgh-laya);
  color: white;
  border-color: var(--lgh-laya);
}
.tok.state {
  color: var(--lgh-muted);
  font-style: italic;
}
.encoding .seq {
  animation: pulse 0.9s ease-in-out 2;
}
@keyframes pulse {
  50% {
    background: rgba(124, 77, 219, 0.18);
  }
}
.encoder {
  margin-top: 4px;
  text-align: center;
  font-weight: 700;
  color: var(--lgh-laya);
  transition: opacity 0.4s ease;
}
.hint {
  margin-top: 8px !important;
  font-size: 11px;
  transition: opacity 0.4s ease;
}
.stats {
  grid-column: 1 / -1;
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  text-align: center;
  border-top: 1px solid var(--lgh-line);
  padding-top: 10px;
  font-size: 12px;
  color: var(--lgh-muted);
  transition: opacity 0.5s ease;
}
.stats .lgh-big {
  font-size: 1.9rem;
  color: var(--lgh-laya);
}
</style>
