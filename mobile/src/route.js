// Что показывать бригаде по маршруту: текущая заявка и какие кнопки у неё.
// Чистые функции — проверяются тестами без браузера.

const MOSCOW_OFFSET_MS = 3 * 60 * 60 * 1000
const WEEKDAYS = ['вс', 'пн', 'вт', 'ср', 'чт', 'пт', 'сб']
const MONTHS = [
  'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
  'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря',
]

// "2026-08-17T15:00:00Z" -> "18:00" по Москве, как бы ни был настроен телефон
export function moscowTime(isoString) {
  if (!isoString) return ''
  return new Date(new Date(isoString).getTime() + MOSCOW_OFFSET_MS).toISOString().slice(11, 16)
}

// "2026-08-17" -> "17 августа, пн"
export function formatDay(day) {
  const date = new Date(`${day}T12:00:00Z`)
  return `${date.getUTCDate()} ${MONTHS[date.getUTCMonth()]}, ${WEEKDAYS[date.getUTCDay()]}`
}

// заявка закрыта: выполнена, отменена или снята с плана — к ней не едем
export function isClosed(visit) {
  return visit.removed || visit.status_code === 'done' || visit.status_code === 'cancelled'
}

// текущая заявка — первая незакрытая по порядку: бригада идёт по маршруту
export function currentVisit(route) {
  return route?.visits.find((visit) => !isClosed(visit)) ?? null
}

// какую главную кнопку показать у текущей заявки
export function nextAction(visit) {
  if (!visit || isClosed(visit)) return null
  if (!visit.departed_at) return { action: 'depart', label: 'Выехали' }
  if (!visit.arrived_at) return { action: 'arrive', label: 'На месте' }
  return { action: 'done', label: 'Выполнено' }
}

// сколько закрыто из маршрута: для полоски прогресса
export function progress(route) {
  const visits = route?.visits.filter((visit) => !visit.removed) ?? []
  const done = visits.filter(isClosed).length
  return { done, total: visits.length }
}

// ссылка на маршрут в Яндекс Картах: от текущего места до заявки
export function mapsLink(visit) {
  return `https://yandex.ru/maps/?rtext=~${visit.latitude},${visit.longitude}&rtt=auto`
}
