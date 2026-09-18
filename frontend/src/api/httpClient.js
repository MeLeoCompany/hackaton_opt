// Общий HTTP-клиент. Все запросы идут на относительный /api — в дев-режиме его проксирует vite.
// Каждый запрос несёт токен входа и выбранный офис (authSession.js); ответ 401 значит,
// что сессия кончилась, — интерфейс возвращается к экрану входа.

import { authHeaders, sessionExpired } from './authSession.js'

export class ApiError extends Error {
  constructor(message, details = []) {
    super(message)
    this.details = details // список понятных причин, например ошибки по строкам CSV
  }
}

const FIELD_LABELS = {
  id: 'Номер',
  address: 'Адрес',
  latitude: 'Широта',
  longitude: 'Долгота',
  duration_minutes: 'Длительность',
  window_start: 'Начало окна',
  window_end: 'Конец окна',
  priority_id: 'Приоритет',
  skill_id: 'Навык',
  transport_id: 'Транспорт',
  is_active: 'Активность',
  status_id: 'Статус',
  request_ids: 'Заявки',
  name: 'Имя',
  start_latitude: 'Широта старта',
  start_longitude: 'Долгота старта',
  shift_start: 'Начало смены',
  shift_end: 'Конец смены',
  skill_ids: 'Навыки',
  plan_date: 'День плана',
  file: 'Файл',
  login: 'Логин',
  password: 'Пароль',
  role: 'Роль',
  office_id: 'Офис',
}

export async function apiRequest(method, path, { json, formData } = {}) {
  const options = { method, headers: authHeaders() }
  if (json !== undefined) {
    options.headers['Content-Type'] = 'application/json'
    options.body = JSON.stringify(json)
  }
  if (formData) {
    options.body = formData
  }

  const response = await fetch(`/api/v1${path}`, options)
  if (response.status === 204) return null

  const body = await response.json().catch(() => null)
  // неверный пароль при входе — тоже 401, но это ошибка формы, а не конец сессии
  if (response.status === 401 && path !== '/auth/login') sessionExpired()
  if (!response.ok) throw toApiError(response.status, body)
  return body
}

export async function apiDownload(path) {
  const response = await fetch(`/api/v1${path}`, { headers: authHeaders() })
  if (response.status === 401) sessionExpired()
  if (!response.ok) throw new ApiError(`Не удалось скачать файл: ${response.status}`)
  return response.blob()
}

// Ответ с ошибкой бывает трёх видов: наш список причин (errors), ошибки проверки полей
// от FastAPI (detail — массив) или просто текст (detail — строка).
function toApiError(status, body) {
  if (Array.isArray(body?.errors)) {
    return new ApiError(body.detail || 'Проверьте данные', body.errors)
  }
  if (Array.isArray(body?.detail)) {
    const details = body.detail.map((problem) => `${fieldLabel(problem.loc)}: ${explain(problem)}`)
    return new ApiError('Проверьте данные заявки', details)
  }
  if (typeof body?.detail === 'string') {
    return new ApiError(body.detail)
  }
  return new ApiError(`Запрос не прошёл: ${status}`)
}

function fieldLabel(location = []) {
  const fieldName = location[location.length - 1]
  return FIELD_LABELS[fieldName] ?? 'Данные'
}

function explain(problem) {
  switch (problem.type) {
    case 'missing':
    case 'string_too_short':
    case 'float_type':
    case 'int_type':
    case 'datetime_type':
      return 'не заполнено'
    case 'float_parsing':
    case 'int_parsing':
      return 'должно быть числом'
    case 'datetime_parsing':
    case 'datetime_from_date_parsing':
      return 'неверные дата и время'
    case 'greater_than':
      return `должно быть больше ${problem.ctx?.gt}`
    case 'greater_than_equal':
      return `должно быть не меньше ${problem.ctx?.ge}`
    case 'less_than_equal':
      return `должно быть не больше ${problem.ctx?.le}`
    case 'value_error':
      return problem.msg.replace(/^Value error, /, '')
    default:
      return problem.msg
  }
}
