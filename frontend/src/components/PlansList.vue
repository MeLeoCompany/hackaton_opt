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
          <th>Не назначено</th>
          <th>Исполнителей</th>
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
          <td class="number-cell">{{ summary.unassigned_count }}</td>
          <td class="number-cell">{{ summary.engineers_used }}</td>
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
