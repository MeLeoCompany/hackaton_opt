// Названия из справочников по номеру. references — { skills, priorities, transports }.

export function referenceName(references, listName, id) {
  if (id === null || id === undefined) return '—'
  return references[listName]?.find((item) => item.id === id)?.name ?? `№${id}`
}

export function isUrgent(references, request) {
  return referenceName(references, 'priorities', request.priority_id) === 'Срочная'
}
