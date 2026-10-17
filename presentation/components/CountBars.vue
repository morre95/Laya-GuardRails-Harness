<script setup lang="ts">
import { computed } from 'vue'
import { formatCount } from '../data/demo'

const props = defineProps<{ counts: Record<string, number>, risky?: string[] }>()

const total = computed(() => Object.values(props.counts).reduce((sum, n) => sum + n, 0))
const largest = computed(() => Math.max(...Object.values(props.counts)))
</script>

<template>
  <div class="counts">
    <div v-for="(count, label) in counts" :key="label" class="row">
      <code>{{ label }}</code>
      <div class="track">
        <div
          class="fill"
          :style="{ width: `${(count / largest) * 100}%`, background: risky?.includes(String(label)) ? 'var(--risk)' : 'var(--seg-state)' }"
        />
      </div>
      <span class="value"><b>{{ formatCount(count) }}</b> <span class="muted">{{ ((count / total) * 100).toFixed(1).replace('.', ',') }} %</span></span>
    </div>
  </div>
</template>

<style scoped>
.counts {
  display: grid;
  gap: 0.35rem;
  font-size: 0.75rem;
}

.row {
  display: grid;
  grid-template-columns: 7.5rem 1fr 6.5rem;
  align-items: center;
  gap: 0.5rem;
}

.track {
  height: 0.7rem;
}

.fill {
  height: 100%;
  min-width: 3px;
  border-radius: 0 3px 3px 0;
}

.value {
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
</style>
