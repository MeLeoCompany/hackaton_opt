// Кто вошёл и в каком офисе работает. Состояние общее на приложение (ref в модуле).
// Диспетчер работает в офисе своей учётки — выбирать нечего. Администратор выбирает офис
// в боковой панели; выбор запоминается в браузере и уходит заголовком в каждый запрос.

import { computed, ref } from 'vue'

import { fetchMe, login as requestLogin } from '../api/authApi.js'
import { hasToken, onSessionExpired, saveOfficeId, saveToken, storedOfficeId } from '../api/authSession.js'
import { listOffices } from '../api/officesApi.js'

const USER_KEY = 'routing.user'

function storedUser() {
  try {
    return hasToken() ? JSON.parse(window.localStorage.getItem(USER_KEY) ?? 'null') : null
  } catch {
    return null
  }
}

function rememberUser(value) {
  try {
    if (value) window.localStorage.setItem(USER_KEY, JSON.stringify(value))
    else window.localStorage.removeItem(USER_KEY)
  } catch {
    // не смогли запомнить — после перезагрузки попросим войти снова
  }
}

const user = ref(storedUser())
// офисы для выбора администратором
const offices = ref([])
const chosenOfficeId = ref(storedOfficeId())

// токен истёк или учётку выключили — возвращаемся ко входу
onSessionExpired(() => {
  user.value = null
  rememberUser(null)
})

export function useAuth() {
  const isAdmin = computed(() => user.value?.role === 'admin')

  const currentOfficeId = computed(() => (isAdmin.value ? chosenOfficeId.value : user.value?.office_id ?? null))

  const currentOfficeName = computed(() => {
    if (!isAdmin.value) return user.value?.office_name ?? ''
    return offices.value.find((office) => office.id === chosenOfficeId.value)?.name ?? ''
  })

  function chooseOffice(officeId) {
    chosenOfficeId.value = officeId
    saveOfficeId(officeId)
  }

  // администратору нужен список офисов; выбранный пропал из справочника — берём первый
  async function loadOffices() {
    if (!isAdmin.value) return
    offices.value = await listOffices()
    if (!offices.value.some((office) => office.id === chosenOfficeId.value)) {
      chooseOffice(offices.value[0]?.id ?? null)
    }
  }

  function applySession(nextUser) {
    user.value = nextUser
    rememberUser(nextUser)
    // у диспетчера офис из учётки: заголовок не нужен и не должен остаться от администратора
    if (nextUser?.role !== 'admin') chooseOffice(null)
  }

  async function login(loginName, password) {
    const session = await requestLogin(loginName, password)
    // учётка бригады работает только в мобильном приложении: здесь бэкенд ей всё запретит
    if (session.user?.role === 'brigade') {
      throw new Error('Это учётка бригады — войдите в мобильное приложение бригады')
    }
    saveToken(session.token)
    applySession(session.user)
    await loadOffices()
  }

  function logout() {
    saveToken(null)
    applySession(null)
    offices.value = []
  }

  // после перезагрузки страницы: сверяем учётку с сервером (роль или офис могли поменять)
  async function restore() {
    if (!hasToken()) {
      applySession(null)
      return
    }
    try {
      applySession(await fetchMe())
      await loadOffices()
    } catch {
      // 401 уже вернул ко входу; сеть недоступна — остаёмся с тем, что помним
    }
  }

  return {
    user,
    offices,
    isAdmin,
    currentOfficeId,
    currentOfficeName,
    chooseOffice,
    loadOffices,
    login,
    logout,
    restore,
  }
}
