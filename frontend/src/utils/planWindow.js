// Пересчёт посчитан на выезд в определённый момент и в этот момент вступает в силу сам:
// до него бригады доезжают по прежнему плану, с него — по новому. Если к этому моменту
// появились новые вводные, пересчёт в силу не вступает и приходит с причиной (void_reason).

import { moscowTimeOf } from './moscowTime.js'

export function approvalWindow(summary, now) {
  if (!summary?.replanned_at || summary.approved_at || summary.superseded_at) return null
  if (summary.voided_at) {
    return {
      state: 'voided',
      text: `не вступил в силу в ${moscowTimeOf(summary.voided_at)}`,
      title: summary.void_reason ?? 'За время расчёта день изменился — пересчитайте заново',
    }
  }
  const minutesLeft = Math.ceil((new Date(summary.replanned_at) - now) / 60_000)
  if (minutesLeft > 0) {
    return {
      state: 'waiting',
      text: `вступит в силу в ${moscowTimeOf(summary.replanned_at)} · через ${minutesLeft} мин`,
      title:
        'До этого момента бригады едут по прежнему плану — это запас на сам расчёт и обзвон ' +
        'клиентов. Пересчёт вступит в силу сам; если он не нужен, удалите его до этого момента',
    }
  }
  return {
    state: 'now',
    text: `вступает в силу в ${moscowTimeOf(summary.replanned_at)}`,
    title: 'Момент, на который считался пересчёт, настал — он вот-вот заменит прежний план',
  }
}
