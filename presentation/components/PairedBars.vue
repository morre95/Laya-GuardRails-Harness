<script setup lang="ts">
export interface PairedRow {
  label: string
  base: number
  tuned: number
  baseText?: string
  tunedText?: string
}

const props = defineProps<{ rows: PairedRow[] }>()

function text(value: number, override?: string): string {
  return override ?? `${Math.round(value * 100)} %`
}
</script>

<template>
  <div class="paired">
    <div class="legend">
      <span><i class="swatch base" />Grundmodell</span>
      <span><i class="swatch tuned" />Finjusterad</span>
    </div>
    <div v-for="row in props.rows" :key="row.label" class="row">
      <div class="label">{{ row.label }}</div>
      <div class="bars">
        <div class="bar">
          <div class="fill base" :style="{ width: `${row.base * 100}%` }" />
          <span class="value">{{ text(row.base, row.baseText) }}</span>
        </div>
        <div class="bar">
          <div class="fill tuned" :style="{ width: `${row.tuned * 100}%` }" />
          <span class="value">{{ text(row.tuned, row.tunedText) }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.paired {
  display: flex;
  flex-direction: column;
  gap: 7px;
  font-size: 12px;
}
.legend {
  display: flex;
  gap: 16px;
  color: var(--lgh-muted);
}
.swatch {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 2px;
  margin-right: 5px;
}
.swatch.base,
.fill.base {
  background: var(--lgh-base);
}
.swatch.tuned,
.fill.tuned {
  background: var(--lgh-laya);
}
.row {
  display: grid;
  grid-template-columns: 170px 1fr;
  align-items: center;
  gap: 10px;
}
.label {
  font-family: var(--slidev-code-font-family, monospace);
  font-size: 11px;
}
.bars {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.bar {
  display: flex;
  align-items: center;
  gap: 6px;
  height: 11px;
}
.fill {
  height: 100%;
  border-radius: 3px;
  min-width: 2px;
}
.value {
  font-size: 10.5px;
  font-weight: 600;
  white-space: nowrap;
}
</style>
