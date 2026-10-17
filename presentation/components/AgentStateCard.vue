<script setup lang="ts">
import type { LayaState } from '../data/demo'

defineProps<{ state: LayaState }>()
</script>

<template>
  <div class="state">
    <div class="field"><span class="name">mål</span>{{ state.goal }}</div>
    <div v-if="state.plan" class="field"><span class="name">plan</span>{{ state.plan }}</div>
    <div class="field">
      <span class="name">repo</span>
      <code>{{ state.repo.branch }}</code>
      <span class="muted"> · ändrad: {{ state.repo.changed.join(', ') || 'inget' }} · {{ state.environment }}</span>
    </div>
    <div class="field">
      <span class="name">senast</span>
      <span class="recent">
        <code v-for="step in state.recent" :key="step">{{ step }}</code>
      </span>
    </div>
    <div class="command">
      <span class="prompt">{{ state.action.tool }} $</span> {{ state.action.command }}
    </div>
  </div>
</template>

<style scoped>
.state {
  border: 1px solid var(--line);
  border-radius: var(--radius);
  overflow: hidden;
  font-size: 0.85rem;
}

.field {
  display: flex;
  align-items: baseline;
  gap: 0.75rem;
  padding: 0.45rem 0.9rem;
  border-bottom: 1px solid var(--line);
  background: var(--panel);
}

.name {
  flex: 0 0 3.5rem;
  color: var(--muted);
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.recent {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
}

.command {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.82rem;
  padding: 0.8rem 0.9rem;
  background: #141a24;
  color: #f4f6fa;
  word-break: break-all;
}

.prompt {
  color: #8ee3c2;
}
</style>
