// Состояние приложения бригады: кто вошёл, выбранный день, маршрут, отметки.

import { ref } from 'vue'

import { ApiError, currentUser, login, markVisit, routeDays, routeOf, storeToken, storedToken } from './api.js'

const user = ref(null)
const days = ref([])
const day = ref(null)
const route = ref(null)
const loading = ref(false)
const busy = ref(false) // отметка уходит на сервер — кнопки ждут
const errorMessage = ref('')
const noticeMessage = ref('')
let noticeTimer = null

function showNotice(text) {
  noticeMessage.value = text
  clearTimeout(noticeTimer)
  noticeTimer = setTimeout(() => {
    noticeMessage.value = ''
  }, 3500)
}

// сессия кончилась — назад ко входу
function handle(error) {
  if (error instanceof ApiError && error.status === 401) {
    logout()
    errorMessage.value = 'Сессия закончилась — войдите заново'
    return
  }
  errorMessage.value = error.message
}

async function signIn(loginName, password) {
  errorMessage.value = ''
  busy.value = true
  try {
    const response = await login(loginName, password)
    if (response.user.role !== 'brigade') {
      errorMessage.value = 'Это приложение для бригад — войдите учёткой бригады'
      return
    }
    storeToken(response.token)
    user.value = response.user
    await loadDays()
  } catch (error) {
    handle(error)
  } finally {
    busy.value = false
  }
}

// открыли приложение с сохранённым входом — проверяем, что он ещё действует
async function restore() {
  if (!storedToken()) return
  try {
    const me = await currentUser()
    if (me.role !== 'brigade') return logout()
    user.value = me
    await loadDays()
  } catch (error) {
    handle(error)
  }
}

function logout() {
  storeToken(null)
  user.value = null
  route.value = null
  days.value = []
  day.value = null
}

async function loadDays() {
  const loaded = await routeDays()
  days.value = loaded.days
  day.value = loaded.default_day
  await loadRoute()
}

async function loadRoute() {
  if (!day.value) {
    route.value = null
    return
  }
  loading.value = true
  try {
    route.value = await routeOf(day.value)
  } catch (error) {
    handle(error)
  } finally {
    loading.value = false
  }
}

async function selectDay(value) {
  day.value = value
  errorMessage.value = ''
  await loadRoute()
}

const DONE_TEXT = {
  depart: 'Выезд отмечен — хорошей дороги',
  arrive: 'Прибытие отмечено',
  done: 'Заявка выполнена',
  fail: 'Отмечено: выполнить нельзя',
}

async function mark(visit, action, reason = '') {
  errorMessage.value = ''
  busy.value = true
  try {
    route.value = await markVisit(visit.request_id, action, reason)
    showNotice(DONE_TEXT[action])
  } catch (error) {
    handle(error)
    // маршрут мог поменяться у диспетчера — показываем актуальный
    await loadRoute()
  } finally {
    busy.value = false
  }
}

export function useBrigade() {
  return {
    user,
    days,
    day,
    route,
    loading,
    busy,
    errorMessage,
    noticeMessage,
    signIn,
    restore,
    logout,
    loadRoute,
    selectDay,
    mark,
  }
}
