<script setup lang="ts">
import { computed } from 'vue'
import type { SequenceLayout } from '../data/demo'
import { formatCount } from '../data/demo'

const props = withDefaults(defineProps<{ layout: SequenceLayout, stateShown?: number }>(), { stateShown: 60 })

type Kind = 'special' | 'head' | 'mask' | 'option' | 'state'

const optionsEnd = computed(() => props.layout.marker_positions[0] + props.layout.options)

const pieces = computed(() => {
  const special = new Set(['[CLS]', '[SEP]'])
  const visible = optionsEnd.value + 1 + props.stateShown
  return props.layout.pieces.slice(0, visible).map((text, index) => {
    let kind: Kind = 'state'
    if (special.has(text))
      kind = 'special'
    else if (props.layout.marker_positions.includes(index))
      kind = 'mask'
    else if (index < props.layout.marker_positions[0])
      kind = 'head'
    else if (index < optionsEnd.value)
      kind = 'option'
    return { text, kind }
  })
})

const hidden = computed(() => props.layout.tokens - pieces.value.length)
</script>

<template>
  <div class="sequence">
    <span v-for="(piece, i) in pieces" :key="i" class="piece" :class="piece.kind">{{ piece.text }}</span>
    <span class="piece more">… +{{ formatCount(hidden) }} tokens till av tillståndet</span>
  </div>
</template>

<style scoped>
.sequence {
  display: flex;
  flex-wrap: wrap;
  gap: 3px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.66rem;
  line-height: 1.2;
}

.piece {
  padding: 1px 3px;
  border-radius: 3px;
  white-space: pre;
}

.special {
  background: var(--ink);
  color: var(--page);
}

.head {
  background: var(--seg-head-soft);
  color: var(--seg-head);
}

.mask {
  background: var(--laya);
  color: white;
  font-weight: 700;
}

.option {
  background: var(--seg-option-soft);
  color: #7a4f05;
}

.state {
  background: var(--seg-state-soft);
  color: #0b5b5b;
}

.more {
  color: var(--muted);
  font-family: Inter, sans-serif;
}
</style>
