<script setup>
// Планы выбранного дня: общая информация строкой, клик выбирает план,
// у каждого — кнопка удаления, чтобы день можно было пересчитать заново.
import { moscowTimeOf } from '../utils/moscowTime.js'

defineProps({
  plans: { type: Array, required: true },
  selectedPlanId: { type: Number, default: null },
  busy: { type: Boolean, default: false },
})
defineEmits(['select', 'remove'])

function distanceLabel(summary) {
  if (summary.total_distance_km === null) return '—'
  const approximate = summary.distance_provider === 'haversine' || summary.distance_provider === 'mixed'
  return `${approximate ? '≈ ' : ''}${summary.total_distance_km.toFixed(1)}`
}

function distanceTitle(summary) {
  if (summary.distance_provider === 'haversine') return 'Приближённо: Valhalla была недоступна'
  if (summary.distance_provider === 'mixed') return 'Часть маршрутов рассчитана приближённо'
  return summary.distance_provider === 'valhalla' ? 'Рассчитано по дорогам через Valhalla' : ''
}

function solveDuration(summary) {
  return summary.solve_duration_ms === null ? '—' : `${summary.solve_duration_ms.toFixed(1)} мс`
}
</script>

<template>
  <div class="table-scroll">
    <table class="data-table">
      <thead>
        <tr>
          <th>№</th>
          <th>Рассчитан</th>
          <th>Решатель</th>
          <th>Назначено</th>
          <th>Срочных</th>
          <th>Не назначено</th>
          <th>Исполнителей</th>
          <th>Пробег, км</th>
          <th>Расчёт</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="summary in plans"
          :key="summary.id"
          :class="{ selected: summary.id === selectedPlanId }"
          @click="$emit('select', summary.id)"
        >
          <td class="number-cell">{{ summary.id }}</td>
          <td class="nowrap">{{ moscowTimeOf(summary.created_at) }}</td>
          <td>{{ summary.solver ?? '—' }}</td>
          <td class="number-cell">{{ summary.assigned_count }}</td>
          <td class="number-cell">{{ summary.urgent_assigned_count ?? '—' }}</td>
          <td class="number-cell">{{ summary.unassigned_count }}</td>
          <td class="number-cell">{{ summary.engineers_used }}</td>
          <td class="number-cell" :title="distanceTitle(summary)">{{ distanceLabel(summary) }}</td>
          <td class="number-cell nowrap">{{ solveDuration(summary) }}</td>
          <td>
            <div class="row-actions">
              <button class="danger" :disabled="busy" @click.stop="$emit('remove', summary)">Удалить</button>
            </div>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
