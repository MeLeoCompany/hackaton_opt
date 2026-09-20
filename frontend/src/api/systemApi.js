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
