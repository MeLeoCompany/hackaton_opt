// Планы на день: какие дни есть, построение плана через cuOpt, выбранный план с маршрутами.

import { ref } from 'vue'

import { buildPlan, getPlan, listPlanningDays, listPlans } from '../api/plansApi.js'
import { fetchReferences } from '../api/referencesApi.js'
import { useMessages } from './useMessages.js'

export function usePlans() {
  const days = ref([]) // [{ plan_date, active_requests }]
  const selectedDay = ref('')
  const plans = ref([]) // планы выбранного дня, новые первыми
  const selectedPlanId = ref(null)
  const plan = ref(null) // выбранный план с маршрутами
  const references = ref({ skills: [], priorities: [], transports: [] })
  // чей маршрут подсвечен на карте и в списке; null — показываем все
  const selectedEngineerId = ref(null)

  const loadingDays = ref(false)
  const loadingPlan = ref(false)
  const building = ref(false)
  const { errorMessage, errorDetails, noticeMessage, showError, showNotice, clearMessages } = useMessages()

  async function loadDays() {
    loadingDays.value = true
    clearMessages()
    try {
      const [loadedReferences, loadedDays] = await Promise.all([fetchReferences(), listPlanningDays()])
      references.value = loadedReferences
      days.value = loadedDays
      if (!selectedDay.value && loadedDays.length) selectedDay.value = loadedDays[0].plan_date
      if (selectedDay.value) await loadPlans()
    } catch (error) {
      showError(error)
    } finally {
      loadingDays.value = false
    }
  }

  async function loadPlans() {
    plans.value = []
    plan.value = null
    selectedPlanId.value = null
    try {
      plans.value = await listPlans(selectedDay.value)
      if (plans.value.length) await selectPlan(plans.value[0].id)
    } catch (error) {
      showError(error)
    }
  }

  async function selectPlan(planId) {
    selectedPlanId.value = planId
    selectedEngineerId.value = null
    loadingPlan.value = true
    try {
      plan.value = await getPlan(planId)
    } catch (error) {
      showError(error)
    } finally {
      loadingPlan.value = false
    }
  }

  async function buildDayPlan() {
    building.value = true
    clearMessages()
    try {
      const summary = await buildPlan(selectedDay.value)
      showNotice(
        `План №${summary.id} построен: назначено ${summary.assigned_count}, ` +
          `не назначено ${summary.unassigned_count}, исполнителей ${summary.engineers_used}`,
      )
      plans.value = await listPlans(selectedDay.value)
      await selectPlan(summary.id)
    } catch (error) {
      showError(error)
    } finally {
      building.value = false
    }
  }

  // повторный клик по тому же исполнителю снимает подсветку
  function selectEngineer(engineerId) {
    selectedEngineerId.value = selectedEngineerId.value === engineerId ? null : engineerId
  }

  return {
    days,
    selectedDay,
    plans,
    selectedPlanId,
    plan,
    references,
    selectedEngineerId,
    loadingDays,
    loadingPlan,
    building,
    errorMessage,
    errorDetails,
    noticeMessage,
    loadDays,
    loadPlans,
    selectPlan,
    buildDayPlan,
    selectEngineer,
  }
}
