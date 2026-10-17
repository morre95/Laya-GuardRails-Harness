<script setup lang="ts">
defineProps<{ current: number }>()

const steps = ['Insamling', 'Trace', 'Triage', 'Etikett', 'Export', 'Finjustering', 'Jämförelse']
</script>

<template>
  <ol class="chain">
    <li
      v-for="(step, index) in steps"
      :key="step"
      :class="{ done: index + 1 < current, active: index + 1 === current }"
    >
      <span class="number">{{ index + 1 }}</span>{{ step }}
    </li>
  </ol>
</template>

<style scoped>
.chain {
  display: flex;
  gap: 0.3rem;
  list-style: none;
  padding: 0;
  margin: 0 0 0.9rem;
  font-size: 0.68rem;
}

li {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.25rem 0.5rem;
  border-radius: 999px;
  background: var(--panel);
  color: var(--faint);
  white-space: nowrap;
  margin: 0;
}

.number {
  display: inline-grid;
  place-items: center;
  width: 1.1rem;
  height: 1.1rem;
  border-radius: 50%;
  background: var(--line);
  color: var(--page);
  font-weight: 700;
  font-size: 0.62rem;
}

li.done {
  color: var(--muted);
}

li.done .number {
  background: var(--muted);
}

li.active {
  background: var(--laya-soft);
  color: var(--laya);
  font-weight: 700;
}

li.active .number {
  background: var(--laya);
}
</style>
