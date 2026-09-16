<script setup>
import { computed } from 'vue'

const props = defineProps({
  plan: { type: Object, required: true },
  comparison: { type: Object, required: true },
})

const optimized = computed(() => (props.plan.solver === 'cuopt' ? props.plan : props.comparison))
const baseline = computed(() => (props.plan.solver === 'baseline' ? props.plan : props.comparison))

const rows = computed(() => [
  {
    label: 'Срочных выполнено',
    baseline: baseline.value.urgent_assigned_count,
    optimized: optimized.value.urgent_assigned_count,
    digits: 0,
  },
  {
    label: 'Всего выполнено',
    baseline: baseline.value.assigned_count,
    optimized: optimized.value.assigned_count,
    digits: 0,
  },
  {
    label: 'Исполнителей',
    baseline: baseline.value.engineers_used,
    optimized: optimized.value.engineers_used,
    digits: 0,
  },
  {
    label: 'Пробег, км',
    baseline: baseline.value.total_distance_km,
    optimized: optimized.value.total_distance_km,
    digits: 1,
  },
  {
    label: 'Расчёт, мс',
    baseline: baseline.value.solve_duration_ms,
    optimized: optimized.value.solve_duration_ms,
    digits: 1,
  },
])

function format(value, digits) {
  return value === null || value === undefined ? '—' : Number(value).toFixed(digits)
}

function difference(row) {
  if (row.baseline === null || row.baseline === undefined || row.optimized === null || row.optimized === undefined) {
    return '—'
  }
  const value = Number(row.optimized) - Number(row.baseline)
  const formatted = Math.abs(value).toFixed(row.digits)
  return value > 0 ? `+${formatted}` : value < 0 ? `−${formatted}` : row.digits ? Number(0).toFixed(row.digits) : '0'
}
</script>

<template>
  <section class="comparison-panel">
    <header>
      <div>
        <h2>Сравнение с простым алгоритмом</h2>
        <p>Одинаковые заявки, исполнители и дорожные матрицы</p>
      </div>
      <span>baseline №{{ baseline.id }} · cuOpt №{{ optimized.id }}</span>
    </header>

    <div class="table-scroll">
      <table class="data-table">
        <thead>
          <tr>
            <th>Метрика</th>
            <th>Baseline</th>
            <th>cuOpt</th>
            <th>Разница cuOpt</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.label">
            <td>{{ row.label }}</td>
            <td class="number-cell">{{ format(row.baseline, row.digits) }}</td>
            <td class="number-cell"><strong>{{ format(row.optimized, row.digits) }}</strong></td>
            <td class="number-cell">{{ difference(row) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<style scoped>
.comparison-panel {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px;
  border: 1px solid #dbeafe;
  border-radius: 8px;
  background: #f8fbff;
}

.comparison-panel header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 12px;
}

.comparison-panel h2,
.comparison-panel p {
  margin: 0;
}

.comparison-panel h2 {
  font-size: 15px;
}

.comparison-panel p,
.comparison-panel header > span {
  color: #64748b;
  font-size: 12px;
}
</style>
