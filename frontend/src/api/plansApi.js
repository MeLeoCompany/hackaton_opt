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

// пересчёт утверждённого плана с момента at (ISO; пусто — сейчас): выполненные и начатые
// заявки остаются за бригадами, остальное раскладывается заново — получается новый план
export function replanPlan(planId, params = {}) {
  return apiRequest('POST', `/plans/${planId}/replan`, { json: params })
}

// пробный пересчёт без сохранения: { assigned_count, unassigned: [{ request_id, address,
// window_start, window_end, status_id, reason }] } — на какие заявки не успеваем
export function previewReplan(planId, params = {}) {
  return apiRequest('POST', `/plans/${planId}/replan/preview`, { json: params })
}

// оператор созвонился с клиентом: бригаде разрешён выезд, хотя она отстаёт (docs/algoV2.md, шаг 9)
export function allowDeparture(planId, requestId) {
  return apiRequest('POST', `/plans/${planId}/visits/${requestId}/departure`)
}

export function cancelPlanApproval(planId) {
  return apiRequest('DELETE', `/plans/${planId}/approval`)
}

// что ждёт расчёт дня: сколько заявок пойдёт и какие заняты утверждённым планом другого дня
export function checkPlanningDay(planDate) {
  return apiRequest('GET', `/plans/day-check?plan_date=${encodeURIComponent(planDate)}`)
}

// режим демонстрации: выбранные маршруты приводятся к плану на текущее системное время
export function syncPlan(planId, engineerIds) {
  return apiRequest('POST', `/plans/${planId}/sync`, { json: { engineer_ids: engineerIds } })
}

// перед утверждением черновика: что предложить клиентам заявок, которые в него не влезли.
// Ответ как у пробного пересчёта; ничего не сохраняется
export function previewApproval(planId, params = {}) {
  return apiRequest('POST', `/plans/${planId}/approval/preview`, { json: params })
}

// решения по невлезшим заявкам применяются, день считается заново — новым черновиком
export function decideApproval(planId, params = {}) {
  return apiRequest('POST', `/plans/${planId}/approval/decisions`, { json: params })
}
