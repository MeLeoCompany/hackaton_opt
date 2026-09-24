// Расчёт посчитан на выезд в определённый момент, и этот момент решает его судьбу.
//
// Пересчёт в свой момент вступает в силу сам: до него бригады доезжают по прежнему плану,
// с него — по новому. Если к моменту появились новые вводные, он в силу не вступает и
// приходит с причиной (void_reason).
//
// Черновик дня в свой момент, наоборот, заканчивается: с него бригады должны были выехать,
// а раз не выехали — маршруты начинались бы в прошлом. Утвердить его можно только до этого
// момента и только пока день не изменился (stale_reason с сервера).

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

export function draftWindow(summary, now) {
  // у пересчёта своя плашка (approvalWindow), у утверждённого и заменённого — своя судьба
  if (!summary?.effective_at || summary.approved_at || summary.parent_plan_id) return null
  if (summary.superseded_at || summary.outdated) return null
  const minutesLeft = Math.ceil((new Date(summary.effective_at) - now) / 60_000)
  if (summary.stale_reason || minutesLeft <= 0) {
    return {
      state: 'expired',
      text: `не утвердить · выезд был в ${moscowTimeOf(summary.effective_at)}`,
      title:
        summary.stale_reason ??
        `Черновик посчитан на выезд в ${moscowTimeOf(summary.effective_at)} — этот момент прошёл. ` +
          'Бригады по нему опаздывают, ещё не выехав: посчитайте день заново',
    }
  }
  return {
    state: 'waiting',
    text: `утвердить до ${moscowTimeOf(summary.effective_at)} · ${minutesLeft} мин`,
    title:
      'День посчитан на выезд в этот момент — запас на сам расчёт, подбор окон и обзвон ' +
      'клиентов. Позже план уже не утвердить: считайте день заново',
  }
}

// черновик, который утверждать поздно или не с теми вводными: кнопки закрыты
export function draftBlocked(summary, now) {
  return draftWindow(summary, now)?.state === 'expired'
}
