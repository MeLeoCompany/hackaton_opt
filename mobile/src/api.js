// Запросы к бэкенду. Токен бригады хранится отдельно от диспетчерского: в одном браузере
// можно держать открытыми оба фронтенда под разными учётками.

const TOKEN_KEY = 'routing.mobile.token'

export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.status = status
  }
}

export function storedToken() {
  try {
    return window.localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

export function storeToken(token) {
  try {
    if (token) window.localStorage.setItem(TOKEN_KEY, token)
    else window.localStorage.removeItem(TOKEN_KEY)
  } catch {
    // без хранилища вход просто не переживёт перезагрузку
  }
}

// понятный текст ошибки: у 422 — первая причина из списка, иначе detail
function errorText(body, status) {
  if (Array.isArray(body?.errors) && body.errors.length) return body.errors.join('; ')
  if (typeof body?.detail === 'string') return body.detail
  if (status >= 500) return 'Сервер недоступен, попробуйте ещё раз'
  return 'Не получилось выполнить действие'
}

export async function apiRequest(method, path, json) {
  const headers = { Accept: 'application/json' }
  const token = storedToken()
  if (token) headers.Authorization = `Bearer ${token}`
  if (json !== undefined) headers['Content-Type'] = 'application/json'
  let response
  try {
    response = await fetch(`/api/v1${path}`, {
      method,
      headers,
      body: json === undefined ? undefined : JSON.stringify(json),
    })
  } catch {
    throw new ApiError('Нет связи с сервером — проверьте интернет', 0)
  }
  const body = response.status === 204 ? null : await response.json().catch(() => null)
  if (!response.ok) throw new ApiError(errorText(body, response.status), response.status)
  return body
}

export const login = (loginName, password) =>
  apiRequest('POST', '/auth/login', { login: loginName, password })
export const currentUser = () => apiRequest('GET', '/auth/me')
export const routeDays = () => apiRequest('GET', '/brigade/days')
export const routeOf = (planDate) => apiRequest('GET', `/brigade/route?plan_date=${encodeURIComponent(planDate)}`)
export const markVisit = (requestId, action, reason) =>
  apiRequest('POST', `/brigade/visits/${requestId}/${action}`, action === 'fail' ? { reason } : undefined)
