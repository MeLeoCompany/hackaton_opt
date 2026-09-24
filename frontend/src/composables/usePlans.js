// Планы на выбранный день и выбранный план с маршрутами.

import { ref, watch } from 'vue'

import {
  allowDeparture as allowDepartureRequest,
  syncPlan,
  approvePlan,
  buildPlan,
  cancelPlanApproval,
  decideApproval as decideApprovalRequest,
  replanPlan,
  checkPlanningDay,
  deletePlan,
  getPlan,
  listPlans,
} from '../api/plansApi.js'
import { fetchReferences } from '../api/referencesApi.js'
import { formatDay, moscowDateOf, moscowTimeOf } from '../utils/moscowTime.js'
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

  // пересчёт утверждённого плана с момента: новый план появляется в списке рядом с ним
  async function replan(summary, params) {
    if (building.value) return
    const day = selectedDay.value
    building.value = true
    clearMessages()
    try {
      const result = await replanPlan(summary.id, params)
      if (day !== selectedDay.value) return
      await refreshDay()
      showNotice(
        `Пересчёт №${result.id} плана №${summary.id} готов: назначено ${result.assigned_count}, ` +
          `не назначено ${result.unassigned_count}. ${decisionsText(params.decisions ?? [])}` +
          `Утвердите его, чтобы заменить план №${summary.id}`,
      )
    } catch (error) {
      showError(error)
    } finally {
      building.value = false
    }
  }

  // решения по невлезшим заявкам перед утверждением. approveAfter — режим «Утвердить»:
  // перенос и отмена только убирают работу из дня, расчёта нет, и план тем же действием
  // утверждается. Без него это «Подобрать окна»: согласие на время добавляет работу, день
  // считается заново — новый черновик смотрят и утверждают отдельно
  async function decideApproval(summary, params, { approveAfter = false } = {}) {
    if (building.value) return
    // обещания клиентам расчёт не удержал: сорвать их можно только с ведома оператора
    if (approveAfter && summary.broken_promises?.length && !window.confirm(promiseQuestion(summary))) {
      return
    }
    const day = selectedDay.value
    building.value = true
    clearMessages()
    try {
      const result = await decideApprovalRequest(summary.id, params)
      if (approveAfter) await approvePlan(result.id)
      if (day !== selectedDay.value) return
      await refreshDay()
      showNotice(
        approveAfter
          ? `План №${result.id} утверждён как есть, без пересчёта: ` +
            `${decisionsText(params.decisions)}его заявки закреплены за этим днём`
          : `Решения учтены в расчёте №${result.id}: назначено ${result.assigned_count}, ` +
            `не назначено ${result.unassigned_count}. ${decisionsText(params.decisions)}` +
            'Пересчёта не было — посмотрите расчёт и утвердите',
      )
    } catch (error) {
      showError(error)
    } finally {
      building.value = false
    }
  }

  // режим демонстрации: выбранные бригады «идут строго по плану» до текущего времени
  const syncing = ref(false)

  async function syncRoutes(engineerIds) {
    if (syncing.value || !plan.value || !engineerIds.length) return
    syncing.value = true
    clearMessages()
    try {
      const report = await syncPlan(plan.value.id, engineerIds)
      plan.value = report.plan
      await refreshDay()
      showNotice(
        `Маршрутов приведено к плану: ${report.routes}. Выполнено ${report.done}, в работе ` +
          `${report.in_progress}, в пути ${report.en_route}, в плане ${report.planned}`,
      )
    } catch (error) {
      showError(error)
    } finally {
      syncing.value = false
    }
  }

  // бригада выбилась из плана, но клиент согласен подождать — выезд открывается вручную
  async function allowDeparture(requestId) {
    if (building.value || !plan.value) return
    building.value = true
    clearMessages()
    try {
      plan.value = await allowDepartureRequest(plan.value.id, requestId)
      showNotice(`Выезд на заявку №${requestId} разрешён`)
    } catch (error) {
      showError(error)
    } finally {
      building.value = false
    }
  }

  async function approve(summary) {
    if (building.value) return
    // обещания клиентам расчёт не удержал: сорвать их можно только с ведома оператора
    if (summary.broken_promises?.length && !window.confirm(promiseQuestion(summary))) return
    // пересчёт заменяет действующий план: бригады перейдут на новый маршрут
    if (
      summary.parent_plan_id &&
      !window.confirm(
        `Применить пересчёт №${summary.id} прямо сейчас, не дожидаясь ` +
          `${moscowTimeOf(summary.replanned_at)}? Он заменит план №${summary.parent_plan_id}: ` +
          'бригады увидят новый маршрут, а заявки, которым не нашлось места, вернутся в «Новые». ' +
          'Маршруты от этого не сдвинутся — они посчитаны на выезд с ' +
          `${moscowTimeOf(summary.replanned_at)}.`,
      )
    ) {
      return
    }
    building.value = true
    clearMessages()
    try {
      await approvePlan(summary.id)
      await refreshDay()
      showNotice(
        summary.parent_plan_id
          ? `Пересчёт №${summary.id} применён и заменил план №${summary.parent_plan_id}`
          : `План №${summary.id} утверждён: его заявки закреплены за этим днём`,
      )
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

  // что стало с заявками, по которым оператор решал: иначе заявка молча исчезает из дня
  function decisionsText(decisions) {
    const listed = (action, describe) =>
      decisions
        .filter((decision) => decision.action === action)
        .map((decision) => `№${decision.request_id}${describe ? ` ${describe(decision)}` : ''}`)
    const agreed = listed('agree', (decision) => `на ${moscowTimeOf(decision.window_start)}`)
    const moved = listed('move', (decision) => `на ${formatDay(moscowDateOf(decision.window_start))}`)
    const cancelled = [...listed('cancel'), ...listed('no_answer')]
    const parts = [
      agreed.length && `согласованы: ${agreed.join(', ')}`,
      moved.length && `перенесены: ${moved.join(', ')}`,
      cancelled.length && `отменены: ${cancelled.join(', ')}`,
    ].filter(Boolean)
    return parts.length ? `${parts.join('; ')}. ` : ''
  }

  // чем расчёт разошёлся с обещаниями клиентам (docs/algoV2.md, шаг 5)
  function promiseQuestion(summary) {
    const lines = summary.broken_promises.map((promise) => {
      const promised = `${moscowTimeOf(promise.promised_from)}–${moscowTimeOf(promise.promised_to)}`
      const fact = promise.planned_start ? `план ставит ${moscowTimeOf(promise.planned_start)}` : 'в план не попала'
      return `№${promise.request_id}: обещали ${promised}, ${fact}`
    })
    return (
      `Утвердить план №${summary.id}? Обещанное клиентам не удерживается:\n${lines.join('\n')}\n` +
      'Утвердите и перезвоните клиентам — или откажитесь и оставьте прежний план.'
    )
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

  // оператор сменил статус заявки в маршруте — показываем его у визита без перезагрузки плана.
  // «Новая» бэкенд отвязывает от плана
  function markVisitStatus(requestId, statusId) {
    const code = references.value.request_statuses?.find((status) => status.id === statusId)?.code
    for (const route of plan.value?.routes ?? []) {
      for (const visit of route.visits) {
        if (visit.request_id !== requestId) continue
        visit.status_id = statusId
        if (code === 'new') visit.approved_plan_id = null
        if (code === 'planned') visit.approved_plan_id = plan.value.id
      }
    }
  }

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
    replan,
    approve,
    decideApproval,
    cancelApproval,
    selectEngineer,
    markVisitStatus,
    allowDeparture,
    syncing,
    syncRoutes,
  }
}
