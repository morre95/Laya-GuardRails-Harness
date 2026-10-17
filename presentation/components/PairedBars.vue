<script setup lang="ts">
export interface PairedRow {
  label: string
  base: number
  tuned: number
  baseText?: string
  tunedText?: string
}

withDefaults(defineProps<{ rows: PairedRow[], max?: number }>(), { max: 1 })
</script>

<template>
  <div class="paired">
    <div class="legend">
      <span><i style="background: var(--base)" /> grundmodell</span>
      <span><i style="background: var(--laya)" /> finjusterad</span>
    </div>
    <div v-for="row in rows" :key="row.label" class="row">
      <div class="label">{{ row.label }}</div>
      <div class="bars">
        <div class="bar">
          <div class="fill" :style="{ width: `${(row.base / max) * 100}%`, background: 'var(--base)' }" />
          <span>{{ row.baseText ?? `${Math.round(row.base * 100)} %` }}</span>
        </div>
        <div class="bar">
          <div class="fill" :style="{ width: `${(row.tuned / max) * 100}%`, background: 'var(--laya)' }" />
          <span>{{ row.tunedText ?? `${Math.round(row.tuned * 100)} %` }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.paired {
  display: grid;
  gap: 0.5rem;
  font-size: 0.75rem;
}

.legend {
  display: flex;
  gap: 1rem;
  color: var(--muted);
  font-size: 0.7rem;
}

.legend i {
  display: inline-block;
  width: 0.7rem;
  height: 0.7rem;
  border-radius: 2px;
  vertical-align: -1px;
}

.row {
  display: grid;
  grid-template-columns: 11rem 1fr;
  align-items: center;
  gap: 0.6rem;
}

.label {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.92em;
}

.bars {
  display: grid;
  gap: 2px;
}

.bar {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  height: 0.8rem;
}

.fill {
  height: 100%;
  min-width: 2px;
  border-radius: 0 3px 3px 0;
}

.bar span {
  font-variant-numeric: tabular-nums;
  font-size: 0.9em;
  white-space: nowrap;
}
</style>
