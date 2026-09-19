// Повод пересчитать утверждённый план: с утверждения часть его заявок сняли (отменили или
// вернули в «Новая»), на его день появились новые заявки или бригады отстают так, что к
// части заявок уже не успеть до конца окна. '' — пересчитывать незачем.
export function replanHint(summary) {
  if (!summary?.approved_at) return ''
  const withdrawn = summary.withdrawn_requests ?? []
  const fresh = summary.new_request_ids ?? []
  const atRisk = summary.at_risk_request_ids ?? []
  const reasons = []
  if (atRisk.length) reasons.push(`бригады не успевают к окну: ${atRisk.map((id) => `№${id}`).join(', ')}`)
  if (withdrawn.length) reasons.push(`сняты с плана: ${withdrawn.map((item) => `№${item.request_id}`).join(', ')}`)
  if (fresh.length) reasons.push(`новые заявки дня: ${fresh.map((id) => `№${id}`).join(', ')}`)
  if (!reasons.length) return ''
  return `Рекомендуется пересчитать план — ${reasons.join('; ')}`
}
