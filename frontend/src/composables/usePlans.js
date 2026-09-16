// Планы на день: какие дни есть, построение плана через cuOpt, выбранный план с маршрутами.

import { ref } from 'vue'

import { buildPlan, deletePlan, getPlan, listPlanningDays, listPlans } from '../api/plansApi.js'
import { fetchReferences } from '../api/referencesApi.js'
import { useMessages } from './useMessages.js'

export function usePlans() {
  const days = ref([]) // [{ plan_date, active_requests }]
  const selectedDay = ref('')
  const plans = ref([]) // планы выбранного дня, новые первыми
  const selectedPlanId = ref(null)
  const plan = ref(null) // выбранный план с маршрутами
  const references = ref({ skills: [], priorities: [], transports: [], work_types: [] })
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

  let listRequest = 0
  let detailRequest = 0

  async function loadPlans() {
    const request = ++listRequest
    ++detailRequest
    loadingPlan.value = false
    const day = selectedDay.value
    plans.value = []
    plan.value = null
    selectedPlanId.value = null
    try {
      const summaries = await listPlans(day)
      if (request !== listRequest) return
      plans.value = summaries
      if (plans.value.length) await selectPlan(plans.value[0].id)
    } catch (error) {
      if (request === listRequest) showError(error)
    }
  }

  async function selectPlan(planId) {
    const request = ++detailRequest
    plan.value = null
    selectedPlanId.value = planId
    selectedEngineerId.value = null
    loadingPlan.value = true
    try {
      const loaded = await getPlan(planId)
      if (request !== detailRequest) return
      plan.value = loaded
    } catch (error) {
      if (request === detailRequest) showError(error)
    } finally {
      if (request === detailRequest) loadingPlan.value = false
    }
  }

  async function buildDayPlan() {
    if (building.value) return
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

  async function removePlan(summary) {
    if (building.value) return
    if (!window.confirm(`Удалить план №${summary.id}? Его назначения будут удалены.`)) return
    building.value = true
    clearMessages()
    try {
      await deletePlan(summary.id)
      plans.value = await listPlans(selectedDay.value)
      plan.value = null
      selectedPlanId.value = null
      if (plans.value.length) await selectPlan(plans.value[0].id)
      showNotice(`План №${summary.id} удалён`)
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
    removePlan,
    selectEngineer,
  }
}
