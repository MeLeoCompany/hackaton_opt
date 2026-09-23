// Повод пересчитать утверждённый план: посчитанный пересчёт не вступил в силу, с утверждения
// часть его заявок сняли (отменили или вернули в «Новая»), на его день появились новые заявки
// (аварийные — отдельно, первыми) или бригады отстают так, что к части заявок уже не успеть
// до конца окна. '' — пересчитывать незачем.
export function replanHint(summary) {
  if (!summary?.approved_at) return ''
  // пересчёт не вступил в силу — самое важное: бригады остались на этом плане
  if (summary.voided_replan_id) {
    return `Пересчёт №${summary.voided_replan_id} не вступил в силу — пересчитайте план заново`
  }
  const withdrawn = summary.withdrawn_requests ?? []
  // аварийные — часть новых: называем их отдельно, в остальных новых не повторяем
  const emergency = summary.urgent_request_ids ?? []
  const fresh = (summary.new_request_ids ?? []).filter((id) => !emergency.includes(id))
  const atRisk = summary.at_risk_request_ids ?? []
  const reasons = []
  if (emergency.length) reasons.push(`новые аварийные заявки: ${emergency.map((id) => `№${id}`).join(', ')}`)
  if (atRisk.length) reasons.push(`бригады не успевают к окну: ${atRisk.map((id) => `№${id}`).join(', ')}`)
  if (withdrawn.length) reasons.push(`сняты с плана: ${withdrawn.map((item) => `№${item.request_id}`).join(', ')}`)
  if (fresh.length) reasons.push(`новые заявки дня: ${fresh.map((id) => `№${id}`).join(', ')}`)
  if (!reasons.length) return ''
  return `Рекомендуется пересчитать план — ${reasons.join('; ')}`
}
