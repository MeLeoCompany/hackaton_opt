import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'

// composable поднимается без Vue и без браузера: ref и localStorage подменяются заглушками
function harness() {
  const file = fs.readFileSync(new URL('../src/composables/usePlanFocus.js', import.meta.url), 'utf8')
  const source = file.slice(file.indexOf('const STORAGE_KEY')).replace('export function', 'function')
  const stored = {}
  const make = new Function(
    'ref',
    'window',
    source + '; return usePlanFocus()',
  )
  return make(
    (value) => ({ value }),
    { localStorage: { setItem: (key, value) => { stored[key] = value } } },
  )
}

test('переход к заявке открывает вкладку заявок', () => {
  const focus = harness()

  focus.openRequest(17)

  assert.equal(focus.activeTab.value, 'requests')
  assert.equal(focus.takeRequestId(), 17)
})

test('номер заявки читается один раз', () => {
  const focus = harness()
  focus.openRequest(17)
  focus.takeRequestId()

  // вернулись на вкладку заявок сами — прошлая заявка больше не подсвечивается
  assert.equal(focus.takeRequestId(), null)
})

test('переходы к плану и к заявке не мешают друг другу', () => {
  const focus = harness()

  focus.openPlan(5)
  focus.openRequest(17)

  assert.equal(focus.activeTab.value, 'requests')
  assert.equal(focus.takePlanId(), 5)
  assert.equal(focus.takeRequestId(), 17)
})

test('из заявки: открывается план и заявка для карты, оба читаются один раз', () => {
  const focus = harness()

  focus.openPlan(22, 50104)

  assert.equal(focus.activeTab.value, 'plans')
  assert.equal(focus.takePlanId(), 22)
  assert.equal(focus.takePlanRequestId(), 50104)
  assert.equal(focus.takePlanRequestId(), null)
})

test('из сравнения: план без выделенной заявки', () => {
  const focus = harness()

  focus.openPlan(7)

  assert.equal(focus.takePlanId(), 7)
  assert.equal(focus.takePlanRequestId(), null)
})
