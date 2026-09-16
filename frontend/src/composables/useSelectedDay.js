// Выбранный день — общий для всех вкладок: и заявки, и смены исполнителей, и план строятся на день.
// Значение одно на всё приложение (ref объявлен в модуле) и переживает перезагрузку страницы.

import { ref } from 'vue'

import { listPlanningDays } from '../api/plansApi.js'

const STORAGE_KEY = 'routing.selectedDay'

export function todayInMoscow() {
  const MOSCOW_OFFSET_MS = 3 * 60 * 60 * 1000
  return new Date(Date.now() + MOSCOW_OFFSET_MS).toISOString().slice(0, 10)
}

function storedDay() {
  try {
    return window.localStorage.getItem(STORAGE_KEY) || ''
  } catch {
    return '' // приватное окно или запрещённые куки — просто начнём с сегодняшнего дня
  }
}

const selectedDay = ref(storedDay() || todayInMoscow())
// дни, на которые есть активные заявки: подсказываем, куда перейти, если на выбранный день пусто
const daysWithRequests = ref([])
let daysLoaded = false

export function useSelectedDay() {
  function selectDay(day) {
    selectedDay.value = day || todayInMoscow()
    try {
      window.localStorage.setItem(STORAGE_KEY, selectedDay.value)
    } catch {
      // не смогли запомнить — не страшно, день просто не переживёт перезагрузку
    }
  }

  // при первом запуске открываем день, на который есть заявки: ближайший будущий, иначе последний
  async function loadDaysWithRequests() {
    if (daysLoaded) return
    daysLoaded = true
    const days = await listPlanningDays()
    daysWithRequests.value = days
    if (storedDay() || !days.length) return

    const dates = days.map((day) => day.plan_date)
    const today = todayInMoscow()
    selectDay(dates.find((date) => date >= today) ?? dates[dates.length - 1])
  }

  return { selectedDay, daysWithRequests, selectDay, loadDaysWithRequests }
}
