// Факт по маршруту бригады — из отметок в мобильном приложении (departed_at, arrived_at,
// finished_at у визита) и статусов заявок. Из этого карта плана красит участки и точки,
// а панель маршрутов пишет, где бригада сейчас.

import { moscowTimeOf } from './moscowTime.js'
import { statusCode } from './requestStatuses.js'

// состояние визита: done | cancelled | removed | moving (едет) | onsite (на месте) | planned
export function visitFactState(visit, references, planId) {
  if (visit.approved_plan_id !== undefined && visit.approved_plan_id !== planId) return 'removed'
  const code = statusCode(references, visit.status_id)
  if (code === 'done') return 'done'
  if (code === 'cancelled') return 'cancelled'
  if (code === 'in_progress') return visit.arrived_at ? 'onsite' : 'moving'
  return 'planned'
}

// где бригада и что делает: { kind, text, visit, previous } — previous — откуда едет
export function brigadeNow(route, references, planId) {
  const states = route.visits.map((visit) => visitFactState(visit, references, planId))
  const active = states.findIndex((state) => state === 'moving' || state === 'onsite')
  if (active >= 0) {
    const visit = route.visits[active]
    return states[active] === 'onsite'
      ? { kind: 'onsite', visit, previous: null, text: `на месте №${visit.request_id} с ${moscowTimeOf(visit.arrived_at)}` }
      : {
          kind: 'moving',
          visit,
          previous: active > 0 ? route.visits[active - 1] : null,
          text: `в пути к №${visit.request_id}${visit.departed_at ? ` с ${moscowTimeOf(visit.departed_at)}` : ''}`,
        }
  }
  const closed = states.filter((state) => state !== 'planned').length
  const doneIndex = states.lastIndexOf('done')
  const lastDone = doneIndex >= 0 ? route.visits[doneIndex] : null
  if (closed === route.visits.length && route.visits.length) {
    return { kind: 'finished', visit: lastDone ?? null, previous: null, text: 'маршрут закрыт' }
  }
  if (lastDone) {
    return { kind: 'waiting', visit: lastDone, previous: null, text: `закрыла №${lastDone.request_id}, ждёт выезда` }
  }
  return { kind: 'start', visit: null, previous: null, text: 'ещё не выехала' }
}

// сколько визитов маршрута закрыто (снятые с плана не считаются)
export function routeProgress(route, references, planId) {
  const states = route.visits.map((visit) => visitFactState(visit, references, planId)).filter((state) => state !== 'removed')
  return { done: states.filter((state) => state === 'done' || state === 'cancelled').length, total: states.length }
}
