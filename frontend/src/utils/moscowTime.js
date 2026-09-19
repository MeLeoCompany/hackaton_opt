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

// Набранное в поле времени -> то, что вообще может быть временем.
// Лишние цифры не принимаются: "18:90" набрать нельзя, а "9" превращается в "09:",
// потому что часа, начинающегося на девятку, не бывает.
// deleting — оператор стирает: двоеточие после часа сам не дописываем, иначе «18:» не стереть —
// стёртое двоеточие тут же возвращалось бы.
export function maskTimeInput(rawValue, { deleting = false } = {}) {
  let masked = ''
  for (const digit of rawValue.replace(/[^0-9]/g, '')) {
    const position = masked.replace(':', '').length
    if (position === 0) {
      masked = digit <= '2' ? digit : `0${digit}:`
    } else if (position === 1) {
      if (masked[0] === '2' && digit > '3') continue
      masked = `${masked}${digit}:`
    } else if (position === 2) {
      if (digit > '5') continue
      masked = `${masked}${digit}`
    } else if (position === 3) {
      masked = `${masked}${digit}`
    }
  }
  if (deleting && masked.endsWith(':') && !rawValue.endsWith(':')) return masked.slice(0, -1)
  return masked
}

// Недобранное время -> "ЧЧ:ММ": "18:" -> "18:00", "9" -> "09:00", пустое остаётся пустым
export function completeTime(maskedValue) {
  if (!maskedValue) return ''
  const [hours, minutes = ''] = maskedValue.split(':')
  return `${hours.padStart(2, '0')}:${minutes.padEnd(2, '0').slice(0, 2)}`
}

// "2026-08-17T18:00" -> { date: "2026-08-17", time: "18:00" }
export function splitMoscowInputValue(inputValue) {
  return { date: (inputValue ?? '').slice(0, 10), time: (inputValue ?? '').slice(11, 16) }
}

// "2026-08-17" + "18:00" -> "2026-08-17T18:00"; без даты или времени — пустая строка
export function joinMoscowInputValue(date, time) {
  return date && time ? `${date}T${time}` : ''
}

const DAY_MS = 24 * 60 * 60 * 1000

function shiftDay(date, milliseconds) {
  return new Date(new Date(`${date}T00:00:00Z`).getTime() + milliseconds).toISOString().slice(0, 10)
}

// "2026-08-17" -> "2026-08-18": окно или смена, перешедшие через полночь; шаг вперёд по дням
export function nextDay(date) {
  return shiftDay(date, DAY_MS)
}

// "2026-08-17" -> "2026-08-16"
export function previousDay(date) {
  return shiftDay(date, -DAY_MS)
}

// окно или смена в таблице выбранного дня: дата и так выбрана на форме, поэтому только время.
// { start: "22:00", end: "02:00", endsNextDay: true } — таблица ставит начало и конец
// каждое под своей половиной фильтра «чч:мм – чч:мм»
export function moscowTimeRangeParts(startIso, endIso) {
  const end = moscowTimeOf(endIso)
  return {
    start: moscowTimeOf(startIso),
    end,
    // ровно 00:00 — полночь того же дня по часам диспетчера, помечать нечего
    endsNextDay: moscowDateOf(endIso) > moscowDateOf(startIso) && end !== '00:00',
  }
}

// окно заявки с датой — для карточек и подсказок на карте: "17.08.2026 18:00–20:00"
export function formatMoscowWindow(startIso, endIso) {
  const startDay = moscowDateOf(startIso)
  const endDay = moscowDateOf(endIso)
  if (startDay === endDay) {
    return `${formatDay(startDay)} ${moscowTimeOf(startIso)}–${moscowTimeOf(endIso)}`
  }
  return `${formatDay(startDay)} ${moscowTimeOf(startIso)} – ${formatDay(endDay)} ${moscowTimeOf(endIso)}`
}
