// Подписи синхронизации дня с планом.

import { formatDay, moscowDateOf, moscowTimeOf } from './moscowTime.js'

// момент синхронизации: в тот же день — только время, в другой — с датой («18.09.2026 00:40»)
export function formatSyncMoment(isoString, planDate) {
  const day = moscowDateOf(isoString)
  const time = moscowTimeOf(isoString)
  return day === planDate ? time : `${formatDay(day)} ${time}`
}

// в каком порядке и под какими заголовками показываем переходы синхронизации
export const SYNC_GROUPS = [
  { code: 'done', title: 'Выполнены по плану' },
  { code: 'in_progress', title: 'Бригада выехала — в работу' },
  { code: 'cancelled', title: 'Окно прошло, в плане нет — отменяются' },
]

// сколько заявок в какой статус ушло: «выполнено 3, в работе 1, отменено 2»
export function syncSummary(transitions, statusCodeOf) {
  const count = (code) => transitions.filter((item) => statusCodeOf(item.to_status_id) === code).length
  const parts = [
    ['выполнено', count('done')],
    ['в работе', count('in_progress')],
    ['отменено', count('cancelled')],
  ].filter(([, value]) => value > 0)
  return parts.length ? parts.map(([label, value]) => `${label} ${value}`).join(', ') : 'статусы менять не пришлось'
}
