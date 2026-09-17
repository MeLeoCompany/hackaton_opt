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
  // выбранные планы в порядке отметки: первый отмеченный — слева, второй — справа
  const selectedIds = ref([])
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
      selectedIds.value = summaries.slice(0, 2).map((summary) => summary.id).reverse()
    } catch (error) {
      if (current === listRequest) showError(error)
    } finally {
      if (current === listRequest) loading.value = false
    }
  }

  const planById = (planId) => plans.value.find((plan) => plan.id === planId) ?? null
  const first = computed(() => planById(selectedIds.value[0]))
  const second = computed(() => planById(selectedIds.value[1]))

  // сравниваются ровно два плана: пока выбраны оба, остальные отмечать нельзя
  const selectionIsFull = computed(() => selectedIds.value.length >= 2)

  function togglePlan(planId) {
    if (selectedIds.value.includes(planId)) {
      selectedIds.value = selectedIds.value.filter((id) => id !== planId)
      return
    }
    if (selectionIsFull.value) return
    selectedIds.value = [...selectedIds.value, planId]
  }

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
    selectedIds,
    selectionIsFull,
    togglePlan,
    first,
    second,
    metrics,
    loading,
    errorMessage,
    errorDetails,
    load,
  }
}
