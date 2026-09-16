import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'

function harness() {
  const source = fs.readFileSync(new URL('../src/composables/usePlans.js', import.meta.url), 'utf8')
    .replace(/^import .*$/mg, '').replace('export function', 'function')
  const details = {}, lists = {}, comparisons = {}, errors = []
  const make = new Function('ref', 'getPlan', 'listPlans', 'getComparison', 'useMessages', source + '; return usePlans()')
  const plans = make(value => ({ value }), id => new Promise(resolve => { details[id] = resolve }),
    day => new Promise(resolve => { lists[day] = resolve }),
    id => new Promise(resolve => { comparisons[id] = resolve }),
    () => ({ showError: error => errors.push(error), clearMessages() {} }))
  return { plans, details, lists, comparisons }
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


test('late comparison cannot overwrite a different selected plan', async () => {
  const { plans, details, comparisons } = harness()
  const first = plans.selectPlan(1)
  details[1]({ id: 1, comparison_id: 'pair' })
  await Promise.resolve()
  const second = plans.selectPlan(2)
  details[2]({ id: 2 }); await second
  comparisons[1]({ baseline: { id: 1 }, optimized: { id: 3 } }); await first
  assert.equal(plans.plan.value.id, 2)
  assert.equal(plans.comparison.value, null)
})

test('saved comparison loads when a paired plan is selected', async () => {
  const { plans, details, comparisons } = harness()
  const selected = plans.selectPlan(1)
  details[1]({ id: 1, comparison_id: 'pair' })
  await Promise.resolve()
  const pair = { baseline: { id: 1 }, optimized: { id: 2 } }
  comparisons[1](pair); await selected
  assert.deepEqual(plans.comparison.value, pair)
  assert.equal(plans.loadingPlan.value, false)
})
