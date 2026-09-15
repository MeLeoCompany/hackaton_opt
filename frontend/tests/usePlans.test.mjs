import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'

function harness() {
  const source = fs.readFileSync(new URL('../src/composables/usePlans.js', import.meta.url), 'utf8')
    .replace(/^import .*$/mg, '').replace('export function', 'function')
  const details = {}, lists = {}, errors = []
  const make = new Function('ref', 'getPlan', 'listPlans', 'useMessages', source + '; return usePlans()')
  const plans = make(value => ({ value }), id => new Promise(resolve => { details[id] = resolve }),
    day => new Promise(resolve => { lists[day] = resolve }),
    () => ({ showError: error => errors.push(error), clearMessages() {} }))
  return { plans, details, lists }
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
