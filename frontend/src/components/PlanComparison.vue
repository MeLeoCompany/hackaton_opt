<script setup>
import { computed } from 'vue'
const props = defineProps({
  comparison: { type: Object, required: true },
  disabled: { type: Boolean, default: false },
})
const emit = defineEmits(['select-plan'])
const rows = computed(() => {
  const engineers = new Map()
  for (const [key, plan] of Object.entries(props.comparison)) {
    for (const route of plan.routes) {
      if (!engineers.has(route.engineer_id)) {
        engineers.set(route.engineer_id, { id: route.engineer_id, name: route.engineer_name, baseline: 0, optimized: 0 })
      }
      engineers.get(route.engineer_id)[key] = route.distance_km
    }
  }
  return [...engineers.values()]
})
const estimated = computed(() => [props.comparison.baseline, props.comparison.optimized]
  .some(plan => plan.routes.some(route => route.provider !== 'valhalla')))
const km = value => `${value.toFixed(2)} км`
</script>

<template>
  <section class="comparison">
    <h2>Сравнение алгоритмов</h2>
    <p>Одинаковые заявки, исполнители и дорожные матрицы. Базовый алгоритм назначает заявки
      по порядку поступления первому подходящему исполнителю, добавляя визиты в конец маршрута.</p>
    <p v-if="estimated" class="warn">Часть пробега оценена по прямой: дорожный сервис недоступен.
      Эти значения нельзя считать точным сравнением пробега.</p>
    <p v-if="comparison.baseline.assigned_count !== comparison.optimized.assigned_count" class="warn">
      Число назначенных заявок различается: меньший пробег сам по себе не означает лучший план.
    </p>
    <div class="table-wrap">
      <table>
        <thead><tr><th>Показатель</th><th>Базовый №{{ comparison.baseline.id }}</th><th>Оптимизированный №{{ comparison.optimized.id }}</th></tr></thead>
        <tbody>
          <tr><th>Назначено</th><td>{{ comparison.baseline.assigned_count }}</td><td>{{ comparison.optimized.assigned_count }}</td></tr>
          <tr><th>Не назначено</th><td>{{ comparison.baseline.unassigned_count }}</td><td>{{ comparison.optimized.unassigned_count }}</td></tr>
          <tr><th>Исполнителей</th><td>{{ comparison.baseline.engineers_used }}</td><td>{{ comparison.optimized.engineers_used }}</td></tr>
          <tr><th>Общий пробег</th><td>{{ km(comparison.baseline.total_distance_km) }}</td><td>{{ km(comparison.optimized.total_distance_km) }}</td></tr>
          <tr v-for="row in rows" :key="row.id"><th>{{ row.name }} · №{{ row.id }}</th><td>{{ km(row.baseline) }}</td><td>{{ km(row.optimized) }}</td></tr>
        </tbody>
      </table>
    </div>
    <p class="muted">0 км также возможны у работающего исполнителя, если адрес совпадает со стартом.</p>
    <div class="actions">
      <button :disabled="disabled" @click="emit('select-plan', comparison.baseline.id)">Показать базовый маршрут</button>
      <button :disabled="disabled" @click="emit('select-plan', comparison.optimized.id)">Показать оптимизированный маршрут</button>
    </div>
  </section>
</template>

<style scoped>
.comparison { border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; }
h2 { margin: 0; font-size: 18px; }
p { font-size: 13px; }
.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; }
th, td { text-align: left; padding: 8px; border-bottom: 1px solid #e2e8f0; }
.actions { display: flex; gap: 8px; flex-wrap: wrap; }
.warn { color: #92400e; }
</style>
