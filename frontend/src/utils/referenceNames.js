// Названия из справочников по номеру. references — { skills, priorities, transports }.

export function referenceName(references, listName, id) {
  if (id === null || id === undefined) return '—'
  return references[listName]?.find((item) => item.id === id)?.name ?? `№${id}`
}

// уровень приоритета: 1 — аварийный (важнее всего), 2 — высокий, 3 — обычный
export const TOP_PRIORITY_LEVEL = 1

export function priorityLevel(references, priorityId) {
  return references.priorities?.find((item) => item.id === priorityId)?.level ?? null
}

export function isUrgent(references, request) {
  return priorityLevel(references, request.priority_id) === TOP_PRIORITY_LEVEL
}

// плашка приоритета окрашивается по уровню: аварийный — красная, высокий — оранжевая
export function priorityBadgeClass(references, priorityId) {
  return ['badge', `priority-${priorityLevel(references, priorityId) ?? 'none'}`]
}
