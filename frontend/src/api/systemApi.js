import { apiRequest } from './httpClient.js'

// { now, real_now, offset_seconds, updated_at, updated_by }
export function fetchSystemTime() {
  return apiRequest('GET', '/system/time')
}

// перемотка: момент (ISO) или сдвиг в секундах; 0 — вернуть настоящее время
export function setSystemTime(payload) {
  return apiRequest('PUT', '/system/time', { json: payload })
}

// параметры системы: версии, подключения, настройки, объёмы данных (только администратор)
export function fetchSystemInfo() {
  return apiRequest('GET', '/system/info')
}

// журнал расчётов офиса: чем считали, сколько заняло и чем кончилось
export function listPlanRuns(limit = 50) {
  return apiRequest('GET', `/system/runs?limit=${limit}`)
}

// идёт ли расчёт прямо сейчас: по нему страница планов возвращает полосу хода
export function fetchActiveRun() {
  return apiRequest('GET', '/system/runs/active')
}

// ход одного расчёта: текущий шаг, процент и события по порядку
export function fetchPlanRun(runId) {
  return apiRequest('GET', `/system/runs/${runId}`)
}

// прервать идущий расчёт: он остановится на ближайшем шаге, ничего не сохранив
export function cancelPlanRun(runId) {
  return apiRequest('POST', `/system/runs/${runId}/cancel`)
}

// параметры расчёта по умолчанию: их подставляет диалог расчёта
export function fetchSolverParams() {
  return apiRequest('GET', '/system/solver')
}

export function saveSolverParams(payload) {
  return apiRequest('PUT', '/system/solver', { json: payload })
}

// режим демонстрации: разрешает переводить время и синхронизировать маршруты с планом
export function setDemoMode(enabled) {
  return apiRequest('PUT', '/system/demo', { json: { enabled } })
}

// кеш ответов R5 (docs/algoCachV1.md): сколько пар матрицы и плеч маршрутов лежит
export function fetchTravelCache() {
  return apiRequest('GET', '/system/travel-cache')
}

// сбросить кеш R5: следующие расчёты спросят R5 заново — после замены карты или расписания
export function clearTravelCache() {
  return apiRequest('DELETE', '/system/travel-cache')
}
