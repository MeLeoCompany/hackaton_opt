export const DEFAULT_OBJECTIVE_ORDER = [
  'urgent_requests',
  'assigned_requests',
  'engineers_used',
  'travel_distance',
]

// Ярусы приоритетов (аварии, обещания, перенесённые) идут первыми всегда — иначе экономия
// бригад перевесила бы аварию (docs/algoV2.md). Диспетчер выбирает, что важнее сразу после них.
const NEXT_GOALS = ['assigned_requests', 'engineers_used', 'travel_distance']

export function objectiveOrder(nextGoal) {
  const rest = NEXT_GOALS.filter((goal) => goal !== nextGoal)
  return ['urgent_requests', nextGoal, ...rest]
}

// подпись политики в списке планов; у старых планов заявки могли стоять выше срочности
export const NEXT_GOAL_NAMES = {
  assigned_requests: 'максимум заявок',
  engineers_used: 'минимум бригад',
  travel_distance: 'минимум пробега',
}

export function objectivePolicyLabel(order) {
  if (!Array.isArray(order) || order.length !== 4) return '—'
  if (order[0] !== 'urgent_requests') return `Максимум заявок · ${NEXT_GOAL_NAMES[order[2]]}`
  return `Срочность · ${NEXT_GOAL_NAMES[order[1]]}`
}

// та же политика коротко — для узкой колонки списка планов: уровни приоритета всегда первые,
// поэтому называем только то, что оператор выбрал после них
export function objectiveGoalLabel(order) {
  if (!Array.isArray(order) || order.length !== 4) return '—'
  if (order[0] !== 'urgent_requests') return `${NEXT_GOAL_NAMES[order[0]]} (старый порядок)`
  return NEXT_GOAL_NAMES[order[1]]
}
