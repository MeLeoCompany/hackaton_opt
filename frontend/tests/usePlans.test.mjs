import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'

function harness() {
  const file = fs.readFileSync(new URL('../src/composables/usePlans.js', import.meta.url), 'utf8')
  // всё до первого объявления — импорты, они заменяются аргументами new Function
  const source = file.slice(file.indexOf('export function')).replace('export function', 'function')
  const details = {}, lists = {}, builds = {}, errors = [], notices = [], approvals = []
  const day = { value: '2026-08-17' }
  // проверку дня тесты подменяют: она может и ответить занятыми заявками, и упасть
  const dayCheck = { respond: async () => ({ plan_date: day.value, active_requests: 0, held_requests: [] }) }
  const make = new Function(
    'ref', 'watch', 'approvePlan', 'buildPlan', 'cancelPlanApproval', 'checkPlanningDay',
    'deletePlan', 'getPlan', 'listPlans', 'fetchReferences', 'useMessages', 'useSelectedDay',
    source + '; return usePlans()')
  const plans = make(
    value => ({ value }), () => {},
    async id => { approvals.push(['approve', id]) },
    day => new Promise(resolve => { builds[day] = resolve }),
    async id => { approvals.push(['cancel', id]) },
    () => dayCheck.respond(),
    async () => {},
    id => new Promise(resolve => { details[id] = resolve }),
    day => new Promise(resolve => { lists[day] = resolve }),
    async () => ({ skills: [], priorities: [], transports: [], work_types: [] }),
    () => ({
      showError: error => errors.push(error),
      showNotice: notice => notices.push(notice),
      clearMessages() {},
    }),
    () => ({ selectedDay: day }))
  return { plans, details, lists, builds, notices, errors, approvals, dayCheck }
}

test('late detail response cannot replace the selected plan', async () => {
  const { plans, details } = harness()
  const first = plans.selectPlan(1), second = plans.selectPlan(2)
  details[2]({ id: 2 }); await second
  details[1]({ id: 1 }); await first
  assert.equal(plans.selectedPlanId.value, 2)
  assert.equal(plans.plan.value.id, 2)
})

test('switching day invalidates pending plan details and lists', async () => {
  const { plans, details, lists } = harness()
  const detail = plans.selectPlan(1)
  plans.selectedDay.value = '2026-08-17'
  const first = plans.loadPlans()
  plans.selectedDay.value = '2026-08-18'
  const second = plans.loadPlans()
  lists['2026-08-18']([]); await second
  lists['2026-08-17']([{ id: 1 }]); await first
  details[1]({ id: 1 }); await detail
  assert.equal(plans.plan.value, null)
  assert.deepEqual(plans.plans.value, [])
  assert.equal(plans.loadingPlan.value, false)
})

test('switching day ignores a completed build for the previous day', async () => {
  const { plans, builds, notices } = harness()
  const build = plans.buildDayPlan()
  plans.selectedDay.value = '2026-08-18'
  builds['2026-08-17']({ id: 7, assigned_count: 3, unassigned_count: 1, engineers_used: 2 })
  await build

  assert.deepEqual(plans.plans.value, [])
  assert.equal(plans.selectedPlanId.value, null)
  assert.deepEqual(notices, [])
})

test('plans load even if the day check fails', async () => {
  const { plans, lists, dayCheck, errors } = harness()
  dayCheck.respond = async () => { throw new Error('day-check недоступен') }
  const load = plans.loadPlans()
  lists['2026-08-17']([{ id: 1 }])
  await load

  assert.deepEqual(plans.plans.value.map(summary => summary.id), [1])
  assert.equal(plans.dayCheck.value, null)
  assert.deepEqual(errors, [])
})

test('approval refreshes the plans and the held requests of the day', async () => {
  const { plans, lists, dayCheck, approvals, notices } = harness()
  const held = { request_id: 16, plan_id: 37, plan_date: '2026-08-18' }
  dayCheck.respond = async () => ({ plan_date: '2026-08-17', active_requests: 10, held_requests: [held] })
  const approve = plans.approve({ id: 5 })
  await Promise.resolve()
  lists['2026-08-17']([{ id: 5, approved_at: '2026-08-17T09:00:00+03:00' }])
  await approve

  assert.deepEqual(approvals, [['approve', 5]])
  assert.deepEqual(plans.dayCheck.value.held_requests, [held])
  assert.equal(plans.plans.value[0].approved_at, '2026-08-17T09:00:00+03:00')
  assert.equal(plans.building.value, false)
  assert.equal(notices.length, 1)
})

test('a late day check of the previous day is dropped', async () => {
  const { plans, dayCheck } = harness()
  let release
  dayCheck.respond = () => new Promise(resolve => { release = resolve })
  plans.loadPlans()
  plans.selectedDay.value = '2026-08-18'
  release({ plan_date: '2026-08-17', active_requests: 3, held_requests: [] })
  await Promise.resolve()

  assert.equal(plans.dayCheck.value, null)
})

test('список планов дня открывается без выбранного плана', async () => {
  const { plans, lists } = harness()
  const load = plans.loadPlans()
  lists['2026-08-17']([{ id: 3 }, { id: 1 }])
  await load

  // сначала список: маршруты плана открываются только по клику
  assert.equal(plans.selectedPlanId.value, null)
  assert.equal(plans.plan.value, null)
})

test('назад к списку: поздний ответ открывавшегося плана не показывается', async () => {
  const { plans, details } = harness()
  const opening = plans.selectPlan(7)

  plans.closePlan()
  details[7]({ id: 7 })
  await opening

  assert.equal(plans.selectedPlanId.value, null)
  assert.equal(plans.plan.value, null)
  assert.equal(plans.loadingPlan.value, false)
})

test('сменённый в маршруте статус виден у визита без перезагрузки плана', async () => {
  const { plans, details } = harness()
  const opening = plans.selectPlan(22)
  details[22]({ id: 22, routes: [{ visits: [{ request_id: 1, status_id: 2 }, { request_id: 2, status_id: 2 }] }] })
  await opening

  plans.markVisitStatus(1, 5)

  assert.deepEqual(plans.plan.value.routes[0].visits.map((visit) => visit.status_id), [5, 2])
})

test('возвращённая в «Новая» заявка снимается с плана, возврат «В план» закрепляет снова', async () => {
  const { plans, details } = harness()
  plans.references.value = { request_statuses: [{ id: 1, code: 'new' }, { id: 2, code: 'planned' }] }
  const opening = plans.selectPlan(22)
  details[22]({ id: 22, routes: [{ visits: [{ request_id: 1, status_id: 4, approved_plan_id: 22 }] }] })
  await opening

  plans.markVisitStatus(1, 1)
  assert.equal(plans.plan.value.routes[0].visits[0].approved_plan_id, null)
  plans.markVisitStatus(1, 2)
  assert.equal(plans.plan.value.routes[0].visits[0].approved_plan_id, 22)
})
