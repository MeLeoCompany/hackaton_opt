<script setup>
// Выбор дня — общий для всех вкладок, поэтому стоит на каждой форме одинаковым блоком.
// Календарь, шаг на день назад и вперёд, возврат к сегодняшнему дню.
import { computed } from 'vue'

import { useSelectedDay } from '../composables/useSelectedDay.js'
import { formatDay, nextDay, previousDay } from '../utils/moscowTime.js'

defineProps({
  // что показываем справа: «активных заявок 10», «исполнителей в смене 7» и т.п.
  summary: { type: String, default: '' },
  disabled: { type: Boolean, default: false },
})

const { selectedDay, daysWithRequests, selectDay } = useSelectedDay()

// ближайший день с активными заявками — чтобы не искать вручную, когда на выбранный день пусто
const nearestDayWithRequests = computed(() => {
  const dates = daysWithRequests.value.map((day) => day.plan_date)
  return dates.find((date) => date >= selectedDay.value) ?? dates[dates.length - 1] ?? ''
})

const dayIsEmpty = computed(
  () => !daysWithRequests.value.some((day) => day.plan_date === selectedDay.value),
)
</script>

<template>
  <section class="day-panel" title="Заявки, смены исполнителей и план берутся на этот день">
    <span class="day-label">День</span>
    <button :disabled="disabled" title="Предыдущий день" @click="selectDay(previousDay(selectedDay))">‹</button>
    <input
      :value="selectedDay"
      type="date"
      :disabled="disabled"
      aria-label="день планирования"
      @change="selectDay($event.target.value)"
    />
    <button :disabled="disabled" title="Следующий день" @click="selectDay(nextDay(selectedDay))">›</button>

    <span v-if="summary" class="muted">{{ summary }}</span>

    <button
      v-if="dayIsEmpty && nearestDayWithRequests && nearestDayWithRequests !== selectedDay"
      class="link"
      :disabled="disabled"
      @click="selectDay(nearestDayWithRequests)"
    >
      активных заявок нет · перейти к {{ formatDay(nearestDayWithRequests) }}
    </button>
  </section>
</template>

<style scoped>
.day-panel {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #f8fafc;
  font-size: 13px;
}

.day-label {
  font-weight: 600;
}

.day-panel input[type='date'] {
  width: 160px;
}
</style>
