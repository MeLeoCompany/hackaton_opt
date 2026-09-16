// Длительность в пути: сколько часов и минут, а не время суток.

// 185.4 -> "3 ч 5 мин", 45 -> "45 мин", 120 -> "2 ч"
export function formatDuration(minutes) {
  const whole = Math.round(minutes)
  const hours = Math.floor(whole / 60)
  const rest = whole % 60
  if (hours === 0) return `${rest} мин`
  return rest === 0 ? `${hours} ч` : `${hours} ч ${rest} мин`
}

// Что диспетчер набрал в поле длительности -> минуты; null, если понять нельзя.
// Понимает "1 ч 30 мин", "1ч30м", "2 ч", "45 мин", "1:30" и просто минуты — "90".
export function parseDuration(rawValue) {
  const text = rawValue.trim().toLowerCase()
  if (!text) return null

  const clock = text.match(/^(\d+):(\d{1,2})$/)
  if (clock) return validMinutes(Number(clock[1]) * 60 + Number(clock[2]), Number(clock[2]))

  if (/^\d+$/.test(text)) return validMinutes(Number(text))

  const parts = text.match(/^(?:(\d+)\s*ч[а-я]*)?\s*(?:(\d+)\s*м[а-я]*)?$/)
  if (!parts || (parts[1] === undefined && parts[2] === undefined)) return null
  const rest = Number(parts[2] ?? 0)
  return validMinutes(Number(parts[1] ?? 0) * 60 + rest, parts[1] === undefined ? undefined : rest)
}

function validMinutes(total, minutePart) {
  if (!Number.isSafeInteger(total) || (minutePart !== undefined && minutePart >= 60)) return null
  return total
}
