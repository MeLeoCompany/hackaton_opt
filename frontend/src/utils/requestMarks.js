// Отметки заявки из разговора с клиентом (docs/algoV2.md, шаг 4): обещанное окно, перенос,
// «требует уточнения» и причина отмены. Они же дают заявке ярус в расчёте.

import { formatDay, moscowDateOf, moscowTimeOf } from './moscowTime.js'
import { statusCode } from './requestStatuses.js'

// значение фильтра статуса «Просроченные»: не статус из справочника, а «Новая» с закрытым окном
export const OVERDUE_FILTER = 'overdue'

// просрочена: всё ещё «Новая», а окно уже закрылось — хвост дня, который никто не решил.
// now — системное время: в режиме демонстрации его перематывают
export function isOverdue(request, references, now) {
  return statusCode(references, request.status_id) === 'new' && new Date(request.window_end) <= now
}

// заявку перенесли с этого дня: в списке дня она остаётся, но работать по ней будут в другой
export function movedAway(request, day) {
  return Boolean(day) && request.moved_from === day && moscowDateOf(request.window_start) !== day
}

// day — день, который открыт в списке: от него зависит, читать отметку «перенесена» как
// «ушла отсюда» или «пришла из другого дня»; overdue — заявка просрочена (isOverdue)
export function requestMarks(request, day = null, overdue = false) {
  const marks = []
  if (overdue) marks.push({ kind: 'overdue', text: 'просрочена' })
  if (request.promised_from) {
    marks.push({
      kind: 'promised',
      text: `согласовано ${moscowTimeOf(request.promised_from)}–${moscowTimeOf(request.promised_to)}`,
    })
  }
  if (movedAway(request, day)) {
    marks.push({ kind: 'moved', text: `перенесена на ${formatDay(moscowDateOf(request.window_start))}` })
  } else if (request.moved_from) {
    marks.push({ kind: 'moved', text: `перенесена с ${formatDay(request.moved_from)}` })
  }
  if (request.needs_followup) marks.push({ kind: 'followup', text: 'требует уточнения — перезвонить' })
  if (request.cancel_reason) marks.push({ kind: 'cancelled', text: `причина: ${request.cancel_reason}` })
  return marks
}
