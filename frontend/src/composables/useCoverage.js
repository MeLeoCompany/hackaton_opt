// Показывать ли зону покрытия — одно состояние на все карты: включил на заявках, увидел
// и на тестовых маршрутах, и при выборе точки. Выбор запоминается между входами.

import { ref, watch } from 'vue'

const STORAGE_KEY = 'routing.coverageShown'

function stored() {
  try {
    return localStorage.getItem(STORAGE_KEY) === '1'
  } catch {
    return false
  }
}

const shown = ref(stored())

watch(shown, (value) => {
  try {
    localStorage.setItem(STORAGE_KEY, value ? '1' : '0')
  } catch {
    // приватный режим браузера: обойдёмся без запоминания
  }
})

export function useCoverage() {
  return { shown }
}
