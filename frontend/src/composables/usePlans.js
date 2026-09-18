// Планы на выбранный день и выбранный план с маршрутами.

import { ref, watch } from 'vue'

import {
  approvePlan,
  buildPlan,
  cancelPlanApproval,
  checkPlanningDay,
  deletePlan,
  getPlan,
  listPlans,
} from '../api/plansApi.js'
import { fetchReferences } from '../api/referencesApi.js'
import { useMessages } from './useMessages.js'
import { useSelectedDay } from './useSelectedDay.js'

export function usePlans() {
  const { selectedDay } = useSelectedDay()
  const plans = ref([]) // планы выбранного дня, новые первыми
  // что ждёт расчёт этого дня: сколько заявок пойдёт и какие заняты утверждённым планом
  // другого дня — из этого интерфейс делает предупреждения
  const dayCheck = ref(null)
  const selectedPlanId = ref(null)
  const plan = ref(null) // выбранный план с маршрутами
  const references = ref({ skills: [], priorities: [], transports: [], work_types: [] })
  // чей маршрут подсвечен на карте и в списке; null — показываем все
  const selectedEngineerId = ref(null)

  const loadingDays = ref(false)
  const loadingPlan = ref(false)
  const building = ref(false)
  const { errorMessage, errorDetails, noticeMessage, showError, showNotice, clearMessages } = useMessages()

  async function load() {
    loadingDays.value = true
    clearMessages()
    try {
      references.value = await fetchReferences()
      await loadPlans()
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
      loadDayCheck(day)
      const summaries = await listPlans(day)
      if (request !== listRequest) return
      plans.value = summaries
    } catch (error) {
      if (request === listRequest) showError(error)
    }
  }

  // Открыть план: страница переходит от списка планов к маршрутам этого плана.
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

  // Назад к списку планов дня. Поздний ответ открывавшегося плана уже ничего не покажет.
  function closePlan() {
    ++detailRequest
    plan.value = null
    selectedPlanId.value = null
    selectedEngineerId.value = null
    loadingPlan.value = false
  }

  async function buildDayPlan(params = {}) {
    if (building.value) return
    const day = selectedDay.value
    building.value = true
    clearMessages()
    try {
      const summary = await buildPlan(day, params)
      if (day !== selectedDay.value) return
      showNotice(
        `План №${summary.id} (${summary.solver}) построен: назначено ${summary.assigned_count}, ` +
          `не назначено ${summary.unassigned_count}, исполнителей ${summary.engineers_used}`,
      )
      const summaries = await listPlans(day)
      if (day !== selectedDay.value) return
      // новый план сверху списка: его видно рядом с остальными и можно сразу сравнить
      plans.value = summaries
    } catch (error) {
      showError(error)
    } finally {
      building.value = false
    }
  }

  async function removePlan(summary) {
    if (building.value) return
    if (!window.confirm(`Удалить план №${summary.id}? Его назначения будут удалены.`)) return
    const day = selectedDay.value
    building.value = true
    clearMessages()
    try {
      await deletePlan(summary.id)
      if (day !== selectedDay.value) return
      const summaries = await listPlans(day)
      if (day !== selectedDay.value) return
      plans.value = summaries
      closePlan()
      showNotice(`План №${summary.id} удалён`)
    } catch (error) {
      showError(error)
    } finally {
      building.value = false
    }
  }

  // Предупреждение о занятых заявках грузим отдельно: список планов не должен ждать его,
  // а если проверка не ответит, планы всё равно покажем.
  async function loadDayCheck(day) {
    dayCheck.value = null
    try {
      const check = await checkPlanningDay(day)
      if (day === selectedDay.value) dayCheck.value = check
    } catch {
      // без предупреждения обойдёмся: планы и расчёт от этого не зависят
    }
  }

  async function approve(summary) {
    if (building.value) return
    building.value = true
    clearMessages()
    try {
      await approvePlan(summary.id)
      await refreshDay()
      showNotice(`План №${summary.id} утверждён: его заявки закреплены за этим днём`)
    } catch (error) {
      showError(error)
    } finally {
      building.value = false
    }
  }

  async function cancelApproval(summary) {
    if (building.value) return
    if (!window.confirm(`Снять утверждение с плана №${summary.id}? Его заявки станут доступны другим дням.`)) return
    building.value = true
    clearMessages()
    try {
      await cancelPlanApproval(summary.id)
      await refreshDay()
      showNotice(`Утверждение плана №${summary.id} снято`)
    } catch (error) {
      showError(error)
    } finally {
      building.value = false
    }
  }

  // после утверждения меняются и планы, и занятые заявки дня
  async function refreshDay() {
    const day = selectedDay.value
    loadDayCheck(day)
    const summaries = await listPlans(day)
    if (day === selectedDay.value) plans.value = summaries
  }

  // сменили день — показываем планы нового дня
  watch(selectedDay, loadPlans)

  // повторный клик по тому же исполнителю снимает подсветку
  function selectEngineer(engineerId) {
    selectedEngineerId.value = selectedEngineerId.value === engineerId ? null : engineerId
  }

  return {
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
    load,
    loadPlans,
    selectPlan,
    closePlan,
    buildDayPlan,
    removePlan,
    dayCheck,
    approve,
    cancelApproval,
    selectEngineer,
  }
}
