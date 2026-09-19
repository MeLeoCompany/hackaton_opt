// Токен входа и выбранный администратором офис: httpClient.js подставляет их в каждый запрос.
// Отдельный модуль без Vue — чтобы HTTP-клиент не зависел от composable входа.

const TOKEN_KEY = 'routing.token'
const OFFICE_KEY = 'routing.officeId'

function read(key) {
  try {
    return window.localStorage.getItem(key)
  } catch {
    return null // приватное окно или запрещённые куки
  }
}

function write(key, value) {
  try {
    if (value === null || value === undefined) window.localStorage.removeItem(key)
    else window.localStorage.setItem(key, String(value))
  } catch {
    // не смогли запомнить — сессия просто не переживёт перезагрузку
  }
}

let token = read(TOKEN_KEY)
let officeId = read(OFFICE_KEY)
const expiredListeners = []

export function hasToken() {
  return Boolean(token)
}

export function saveToken(value) {
  token = value
  write(TOKEN_KEY, value)
}

// офис, выбранный администратором; у диспетчера сервер берёт офис из учётки и заголовок не нужен
export function saveOfficeId(value) {
  officeId = value
  write(OFFICE_KEY, value)
}

export function storedOfficeId() {
  return officeId === null ? null : Number(officeId)
}

export function authHeaders() {
  const headers = {}
  if (token) headers.Authorization = `Bearer ${token}`
  if (officeId) headers['X-Office-Id'] = String(officeId)
  return headers
}

// сервер ответил 401: токен истёк или учётку выключили — интерфейс возвращается ко входу
export function onSessionExpired(listener) {
  expiredListeners.push(listener)
}

export function sessionExpired() {
  saveToken(null)
  for (const listener of expiredListeners) listener()
}
