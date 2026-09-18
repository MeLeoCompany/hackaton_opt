import { apiRequest } from './httpClient.js'

// [{ plan_date: '2026-08-17', active_requests: 8 }]
export function listPlanningDays() {
  return apiRequest('GET', '/plans/days')
}

export function listPlans(planDate) {
  return apiRequest('GET', `/plans?plan_date=${encodeURIComponent(planDate)}`)
}

// строит один план; params содержит solver и строгий objective_order для cuOpt
export function buildPlan(planDate, params = {}) {
  return apiRequest('POST', '/plans', { json: { plan_date: planDate, ...params } })
}

export function getPlan(planId) {
  return apiRequest('GET', `/plans/${planId}`)
}

export function deletePlan(planId) {
  return apiRequest('DELETE', `/plans/${planId}`)
}

// утверждение плана: его заявки закрепляются за днём и другим дням не достаются
export function approvePlan(planId) {
  return apiRequest('POST', `/plans/${planId}/approval`)
}

export function cancelPlanApproval(planId) {
  return apiRequest('DELETE', `/plans/${planId}/approval`)
}

// что ждёт расчёт дня: сколько заявок пойдёт и какие заняты утверждённым планом другого дня
export function checkPlanningDay(planDate) {
  return apiRequest('GET', `/plans/day-check?plan_date=${encodeURIComponent(planDate)}`)
}

// до какого времени статусы заявок дня синхронизированы с планом: { synced_to, synced_at, user_name }
export function getDaySync(planDate) {
  return apiRequest('GET', `/plans/day-sync?plan_date=${encodeURIComponent(planDate)}`)
}

// что сделает синхронизация дня на это время — ничего не меняя; syncTime — ISO с поясом
export function previewDaySync(planDate, syncTime) {
  return apiRequest('POST', '/plans/day-sync/preview', { json: { plan_date: planDate, sync_time: syncTime } })
}

// синхронизировать: статусы заявок дня приводятся к утверждённому плану на это время
export function runDaySync(planDate, syncTime) {
  return apiRequest('POST', '/plans/day-sync', { json: { plan_date: planDate, sync_time: syncTime } })
}
