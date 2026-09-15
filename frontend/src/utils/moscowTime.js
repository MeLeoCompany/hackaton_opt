// Диспетчер работает по московскому времени (UTC+3, перехода на летнее время нет).
// В базе время хранится в UTC. Переводим явно, не полагаясь на часовой пояс браузера:
// у диспетчера на ноутбуке может стоять любой.

const MOSCOW_OFFSET_MS = 3 * 60 * 60 * 1000

// Сдвигаем момент на +3 часа: в UTC-записи результата окажутся московские дата и время.
function asMoscowIso(isoString) {
  return new Date(new Date(isoString).getTime() + MOSCOW_OFFSET_MS).toISOString()
}

// "2026-08-17T15:00:00Z" -> "2026-08-17" — московская дата
export function moscowDateOf(isoString) {
  return asMoscowIso(isoString).slice(0, 10)
}

// "2026-08-17T15:00:00Z" -> "18:00" — московское время
export function moscowTimeOf(isoString) {
  return asMoscowIso(isoString).slice(11, 16)
}

// "2026-08-17" -> "17.08.2026"
export function formatDay(day) {
  return `${day.slice(8, 10)}.${day.slice(5, 7)}.${day.slice(0, 4)}`
}

// "2026-08-17T15:00:00Z" -> "2026-08-17T18:00" (значение для <input type="datetime-local">)
export function toMoscowInputValue(isoString) {
  return asMoscowIso(isoString).slice(0, 16)
}

// "2026-08-17T18:00" из поля ввода -> "2026-08-17T18:00:00+03:00" для API
export function fromMoscowInputValue(inputValue) {
  return `${inputValue}:00+03:00`
}

// окно заявки для таблицы: "17.08.2026 18:00–20:00"
export function formatMoscowWindow(startIso, endIso) {
  const startDay = moscowDateOf(startIso)
  const endDay = moscowDateOf(endIso)
  if (startDay === endDay) {
    return `${formatDay(startDay)} ${moscowTimeOf(startIso)}–${moscowTimeOf(endIso)}`
  }
  return `${formatDay(startDay)} ${moscowTimeOf(startIso)} – ${formatDay(endDay)} ${moscowTimeOf(endIso)}`
}
