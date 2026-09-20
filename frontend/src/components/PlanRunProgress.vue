<script setup>
// Ход расчёта: полоса, текущий шаг и последние строки журнала. Большой день считается
// минутами (матрицы Valhalla и R5, cuOpt, проверка расписания) — без этого интерфейс
// выглядит зависшим.
import { computed } from 'vue'

import { moscowTimeOf } from '../utils/moscowTime.js'

const props = defineProps({
  run: { type: Object, default: null }, // ответ /system/runs/{id}; null — журнал ещё не ответил
})

const percent = computed(() => Math.min(100, Math.max(0, props.run?.progress ?? 0)))
const step = computed(() => props.run?.step || 'Готовлю расчёт')
// последние строки: интереснее всего то, что происходит прямо сейчас
const lastEvents = computed(() => (props.run?.events ?? []).slice(-6).reverse())

function seconds(value) {
  return `${Math.round(value ?? 0)} с`
}
</script>

<template>
  <section class="run" role="status" aria-live="polite">
    <div class="run-head">
      <strong>{{ step }}</strong>
      <span class="muted">{{ percent }}% · {{ seconds(run?.duration_seconds) }}</span>
    </div>
    <div class="bar">
      <span :style="{ width: `${percent}%` }"></span>
    </div>
    <ol v-if="lastEvents.length" class="events">
      <li v-for="(event, index) in lastEvents" :key="index" :class="event.level">
        <span class="at">{{ moscowTimeOf(event.at) }}</span>
        <span>{{ event.message }}</span>
      </li>
    </ol>
  </section>
</template>

<style scoped>
.run {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px 12px;
  border: 1px solid #bfdbfe;
  border-radius: 8px;
  background: #f8fbff;
}

.run-head {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: space-between;
  font-size: 13px;
}

.bar {
  height: 8px;
  border-radius: 999px;
  background: #e2e8f0;
  overflow: hidden;
}

.bar span {
  display: block;
  height: 100%;
  border-radius: 999px;
  background: #2563eb;
  transition: width 0.3s ease;
}

.events {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin: 0;
  padding: 0;
  list-style: none;
  color: #475569;
  font-size: 12px;
}

.events li {
  display: flex;
  gap: 8px;
}

.events li.warning {
  color: #b45309;
}

.events li.error {
  color: #b91c1c;
}

.at {
  flex: none;
  color: #94a3b8;
  font-variant-numeric: tabular-nums;
}

.muted {
  color: #64748b;
}
</style>
