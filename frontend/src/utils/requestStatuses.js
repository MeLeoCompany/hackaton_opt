// Статусы заявки из справочника (GET /references: request_statuses, request_status_transitions).
// Статус меняется только переходами из таблицы; оператору доступны переходы с manual.

import { referenceName } from './referenceNames.js'

// порядок, в котором заявка проходит статусы, — для сортировки и списков
const STATUS_FLOW = ['new', 'planned', 'in_progress', 'done', 'cancelled']

export function statusCode(references, statusId) {
  return references.request_statuses?.find((status) => status.id === statusId)?.code ?? ''
}

export function statusIdByCode(references, code) {
  return references.request_statuses?.find((status) => status.code === code)?.id ?? null
}

export function statusPlannable(references, statusId) {
  return references.request_statuses?.find((status) => status.id === statusId)?.plannable ?? false
}

export function statusRank(references, statusId) {
  const index = STATUS_FLOW.indexOf(statusCode(references, statusId))
  return index < 0 ? STATUS_FLOW.length : index
}

// статусы справочника в порядке работы с заявкой
export function orderedStatuses(references) {
  return [...(references.request_statuses ?? [])].sort(
    (first, second) => statusRank(references, first.id) - statusRank(references, second.id),
  )
}

// куда оператор может перевести заявку из этого статуса: [{ to_status_id, name, description }].
// «В плане» руками — только возврат отменённой заявки на её место в утверждённом плане:
// без плана (planId пуст) этот переход не предлагаем
export function manualTransitions(references, fromStatusId, planId = null) {
  const plannedId = statusIdByCode(references, 'planned')
  return (references.request_status_transitions ?? [])
    .filter((transition) => transition.manual && transition.from_status_id === fromStatusId)
    .filter((transition) => transition.to_status_id !== plannedId || planId !== null)
    .map((transition) => ({ ...transition, name: referenceName(references, 'request_statuses', transition.to_status_id) }))
    .sort((first, second) => statusRank(references, first.to_status_id) - statusRank(references, second.to_status_id))
}
