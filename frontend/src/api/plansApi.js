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
