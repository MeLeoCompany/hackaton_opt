import { apiRequest } from './httpClient.js'

// [{ plan_date: '2026-08-17', active_requests: 8 }]
export function listPlanningDays() {
  return apiRequest('GET', '/plans/days')
}

export function listPlans(planDate) {
  return apiRequest('GET', `/plans?plan_date=${encodeURIComponent(planDate)}`)
}

// строит план на день через cuOpt; отвечает сводкой построенного плана
export function buildPlan(planDate, solver = 'cuopt') {
  return apiRequest('POST', '/plans', { json: { plan_date: planDate, solver } })
}

export function getPlan(planId) {
  return apiRequest('GET', `/plans/${planId}`)
}


export function buildComparison(planDate) {
  return apiRequest('POST', '/plans/compare', { json: { plan_date: planDate } })
}

export function getComparison(planId) {
  return apiRequest('GET', `/plans/${planId}/comparison`)
}
