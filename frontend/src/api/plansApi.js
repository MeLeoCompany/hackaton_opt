import { apiRequest } from './httpClient.js'

// [{ plan_date: '2026-08-17', active_requests: 8 }]
export function listPlanningDays() {
  return apiRequest('GET', '/plans/days')
}

export function listPlans(planDate) {
  return apiRequest('GET', `/plans?plan_date=${encodeURIComponent(planDate)}`)
}

// строит сравнимую пару baseline/cuOpt; отвечает сводкой оптимизированного плана
// params — параметры расчёта, пока только { solver: 'cuopt' | 'baseline' }
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
