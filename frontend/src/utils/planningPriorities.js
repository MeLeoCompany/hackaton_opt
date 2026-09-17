export const DEFAULT_OBJECTIVE_ORDER = [
  'urgent_requests',
  'assigned_requests',
  'engineers_used',
  'travel_distance',
]

export function objectiveOrder(servicePriority, resourcePriority) {
  const service =
    servicePriority === 'assigned_requests'
      ? ['assigned_requests', 'urgent_requests']
      : ['urgent_requests', 'assigned_requests']
  const resources =
    resourcePriority === 'travel_distance'
      ? ['travel_distance', 'engineers_used']
      : ['engineers_used', 'travel_distance']
  return [...service, ...resources]
}

export function objectivePolicyLabel(order) {
  if (!Array.isArray(order) || order.length !== 4) return '—'
  const service = order[0] === 'assigned_requests' ? 'Максимум заявок' : 'Срочность'
  const resources = order[2] === 'travel_distance' ? 'минимум пробега' : 'минимум бригад'
  return `${service} · ${resources}`
}
