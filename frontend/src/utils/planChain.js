// Цепочка планов дня: исходный план и его утверждённые пересчёты по порядку — по ней видно,
// что происходило за день (docs/algoV2.md). Один план — цепочки нет, показывать нечего.

export function planChain(plans, planId) {
  const byId = new Map(plans.map((plan) => [plan.id, plan]))
  let first = byId.get(planId)
  if (!first) return []
  while (first.parent_plan_id && byId.has(first.parent_plan_id)) first = byId.get(first.parent_plan_id)

  const chain = [first]
  let next = first.replaced_by_plan_id
  while (next && byId.has(next)) {
    chain.push(byId.get(next))
    next = chain.at(-1).replaced_by_plan_id
  }
  // открытый пересчёт ещё не утверждён: в цепочку его никто не привязал, но показать надо
  if (!chain.some((plan) => plan.id === planId)) chain.push(byId.get(planId))
  return chain.length > 1 ? chain : []
}
