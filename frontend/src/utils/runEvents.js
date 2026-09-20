// Журнал расчёта приходит плоским списком строк со ссылкой на родителя (`parent_id`).
// Здесь он превращается в дерево: шаг — узел, внутри него подробности этого шага,
// строки cuOpt, R5 и Valhalla (db/init/039).

export function eventTree(events = []) {
  const nodes = new Map(events.map((event) => [event.id, { ...event, children: [] }]))
  const roots = []
  for (const event of events) {
    const node = nodes.get(event.id)
    const parent = event.parent_id ? nodes.get(event.parent_id) : null
    if (parent) parent.children.push(node)
    else roots.push(node)
  }
  return roots
}

// худший статус ветки: у свёрнутого шага сразу видно, что внутри была ошибка
export function worstLevel(node) {
  const levels = ['info', 'warning', 'error']
  return (node.children ?? []).reduce(
    (worst, child) => (levels.indexOf(worstLevel(child)) > levels.indexOf(worst) ? worstLevel(child) : worst),
    node.level ?? 'info',
  )
}

export function durationText(node) {
  if (node.duration_ms === null || node.duration_ms === undefined) return ''
  return node.duration_ms < 1000 ? `${node.duration_ms} мс` : `${(node.duration_ms / 1000).toFixed(1)} с`
}
