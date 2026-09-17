<script setup>
// Планы выбранного дня: общая информация строкой, клик выбирает план,
// у каждого — кнопка удаления, чтобы день можно было пересчитать заново.
import { computed } from 'vue'

import { formatDay, moscowTimeOf } from '../utils/moscowTime.js'

const props = defineProps({
  plans: { type: Array, required: true },
  selectedPlanId: { type: Number, default: null },
  busy: { type: Boolean, default: false },
  // заявки дня, занятые утверждённым планом другого дня — о них предупреждаем у каждой строки
  heldRequests: { type: Array, default: () => [] },
})
defineEmits(['select', 'remove', 'approve', 'cancel-approval'])

// одно и то же предупреждение для всех планов дня: их считали без этих заявок
const heldWarning = computed(() => {
  if (!props.heldRequests.length) return ''
  const holders = [...new Set(props.heldRequests.map((held) => `№${held.plan_id} от ${formatDay(held.plan_date)}`))]
  const numbers = props.heldRequests.map((held) => `№${held.request_id}`).join(', ')
  return (
    `Заявок этого дня закреплено за утверждёнными планами других дней: ${props.heldRequests.length} ` +
    `(${numbers}). Забрали: ${holders.join(', ')}. В расчёт этого дня они не идут — ` +
    'чтобы одну заявку не выполнили дважды.'
  )
})

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
          <th>Утверждён</th>
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
          <td class="number-cell nowrap">
            {{ summary.id }}
            <span v-if="heldWarning" class="held-warning" :title="heldWarning">!</span>
          </td>
          <td class="nowrap">{{ moscowTimeOf(summary.created_at) }}</td>
          <td>{{ summary.solver ?? '—' }}</td>
          <td class="number-cell">{{ summary.assigned_count }}</td>
          <td class="number-cell">{{ summary.urgent_assigned_count ?? '—' }}</td>
          <td class="number-cell">{{ summary.unassigned_count }}</td>
          <td class="number-cell">{{ summary.engineers_used }}</td>
          <td class="number-cell" :title="distanceTitle(summary)">{{ distanceLabel(summary) }}</td>
          <td class="number-cell nowrap">{{ solveDuration(summary) }}</td>
          <td class="nowrap">
            <span v-if="summary.approved_at" class="badge approved" title="Заявки этого плана закреплены за днём">
              {{ moscowTimeOf(summary.approved_at) }}
            </span>
            <span v-else class="muted">—</span>
          </td>
          <td>
            <div class="row-actions">
              <button
                v-if="summary.approved_at"
                :disabled="busy"
                title="Снять утверждение: заявки станут доступны другим дням"
                @click.stop="$emit('cancel-approval', summary)"
              >
                Снять
              </button>
              <button
                v-else
                :disabled="busy"
                title="Утвердить план: его заявки закрепятся за этим днём"
                @click.stop="$emit('approve', summary)"
              >
                Утвердить
              </button>
              <button class="danger" :disabled="busy" @click.stop="$emit('remove', summary)">Удалить</button>
            </div>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
/* предупреждение у каждой строки: план считался без заявок, занятых другим днём */
.held-warning {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  margin-left: 6px;
  border-radius: 50%;
  background: #f59e0b;
  color: #fff;
  font-size: 11px;
  font-weight: 700;
  cursor: help;
}

.badge.approved {
  background: #dcfce7;
  color: #166534;
}
</style>
