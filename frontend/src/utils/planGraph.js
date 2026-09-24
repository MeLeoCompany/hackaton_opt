// Как расчёты дня выросли друг из друга: 303 —пересчёт→ 305 —подбор окон→ 306.
//
// У каждого расчёта не больше одного источника: расчёт с решениями оператора вырос из того,
// по чьим невлезшим заявкам эти решения приняты, а пересчёт — из плана, который он пересчитывает.
// Граф читается слева направо по времени.

const BY_DECISIONS = 'подбор окон'
const BY_REPLAN = 'пересчёт'

function originOf(plan) {
  if (plan.decisions_from_plan_id) return { id: plan.decisions_from_plan_id, link: BY_DECISIONS }
  if (plan.parent_plan_id) return { id: plan.parent_plan_id, link: BY_REPLAN }
  return null
}

// Граф расчётов дня для картинки: слева первый расчёт, вправо — во что он превратился.
// Ветка вниз — то, что пошло в сторону: пересчёт, не вступивший в силу, или брошенный черновик.
// Возвращает узлы с колонкой (поколение), строкой (ветка) и подписью связи.
export function planGraph(plans) {
  const byId = new Map(plans.map((plan) => [plan.id, plan]))
  const from = (plan) => {
    const source = originOf(plan)
    return source && byId.has(source.id) ? source : null
  }
  const children = new Map()
  const roots = []
  for (const plan of [...plans].sort((a, b) => a.id - b.id)) {
    const source = from(plan)
    if (source) children.set(source.id, [...(children.get(source.id) ?? []), plan])
    else roots.push(plan)
  }
  // ветка с действующим планом идёт по прямой, остальные уходят вниз
  const working = (plan) => {
    if (plan.approved_at && !plan.superseded_at) return true
    return (children.get(plan.id) ?? []).some(working)
  }
  const nodes = []
  let rows = 0
  const walk = (plan, col, row, edge) => {
    nodes.push({ plan, col, row, edge })
    const kids = [...(children.get(plan.id) ?? [])].sort(
      (a, b) => Number(working(b)) - Number(working(a)) || a.id - b.id,
    )
    kids.forEach((kid, index) => {
      const kidRow = index === 0 ? row : rows++
      walk(kid, col + 1, kidRow, { label: from(kid).link, up: kidRow - row })
    })
  }
  roots.forEach((plan) => walk(plan, 0, rows++, null))
  return { nodes, rows: Math.max(rows, 1), columns: Math.max(...nodes.map((n) => n.col + 1), 1) }
}
