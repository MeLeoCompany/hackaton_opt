// Сравнение двух планов выбранного дня: метрики берутся из сводок планов дня и считается
// разница. Подробности по заявкам и маршрутам живут в самом плане, здесь их не дублируем.

import { computed, ref, watch } from 'vue'

import { listPlans } from '../api/plansApi.js'
import { useMessages } from './useMessages.js'
import { useSelectedDay } from './useSelectedDay.js'

// чем больше — тем лучше, кроме отмеченных lessIsBetter
export const COMPARED_METRICS = [
  { key: 'urgent_assigned_count', label: 'Срочных выполнено', digits: 0 },
  { key: 'assigned_count', label: 'Всего выполнено', digits: 0 },
  { key: 'unassigned_count', label: 'Не назначено', digits: 0, lessIsBetter: true },
  { key: 'engineers_used', label: 'Исполнителей', digits: 0, lessIsBetter: true },
  { key: 'total_distance_km', label: 'Пробег, км', digits: 1, lessIsBetter: true },
  { key: 'solve_duration_ms', label: 'Время расчёта, мс', digits: 1, lessIsBetter: true },
]

export function usePlanComparison() {
  const { selectedDay } = useSelectedDay()
  const plans = ref([]) // планы выбранного дня, новые первыми
  const firstId = ref(null)
  const secondId = ref(null)
  const loading = ref(false)
  const { errorMessage, errorDetails, showError, clearMessages } = useMessages()

  let listRequest = 0

  async function load() {
    const current = ++listRequest
    const day = selectedDay.value
    loading.value = true
    clearMessages()
    try {
      const summaries = await listPlans(day)
      if (current !== listRequest) return
      plans.value = summaries
      // по умолчанию сравниваем два последних плана дня — обычно это разные алгоритмы
      firstId.value = summaries[1]?.id ?? null
      secondId.value = summaries[0]?.id ?? null
    } catch (error) {
      if (current === listRequest) showError(error)
    } finally {
      if (current === listRequest) loading.value = false
    }
  }

  const first = computed(() => plans.value.find((plan) => plan.id === firstId.value) ?? null)
  const second = computed(() => plans.value.find((plan) => plan.id === secondId.value) ?? null)

  const metrics = computed(() => {
    if (!first.value || !second.value) return []
    return COMPARED_METRICS.map((metric) => {
      const firstValue = first.value[metric.key]
      const secondValue = second.value[metric.key]
      const difference =
        firstValue === null || secondValue === null ? null : secondValue - firstValue
      return { ...metric, first: firstValue, second: secondValue, difference }
    })
  })

  // сменили день — планы берутся уже на новый день
  watch(selectedDay, load)

  return {
    plans,
    firstId,
    secondId,
    first,
    second,
    metrics,
    loading,
    errorMessage,
    errorDetails,
    load,
  }
}
