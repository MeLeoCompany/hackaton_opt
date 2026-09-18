import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'

// чистая функция columnWidths — без Vue: достаём её из файла composable
const file = fs.readFileSync(new URL('../src/composables/useColumnWidths.js', import.meta.url), 'utf8')
const source = file
  .slice(file.indexOf('function preferred'), file.indexOf('// ширины колонок для таблицы внутри container'))
  .replace('export function', 'function')
const columnWidths = new Function(source + '; return columnWidths')()

const COLUMNS = [
  { key: 'id', width: '100px' },
  { key: 'address', grow: 3, minWidth: 180, floor: 120 },
  { key: 'coordinates', width: '140px', floor: 90 },
  { key: 'work', grow: 1, minWidth: 150, floor: 110 },
  { key: 'actions', width: '130px' },
]
const total = (widths) => Object.values(widths).reduce((sum, width) => sum + width, 0)

test('широкое окно: компактные своей ширины, остаток растущим по весам', () => {
  const widths = columnWidths(COLUMNS, 1100)

  assert.equal(widths.id, 100)
  assert.equal(widths.coordinates, 140)
  assert.equal(widths.address - 180, 3 * (widths.work - 150))
  assert.ok(total(widths) <= 1100)
})

test('окно поуже: сужаются только колонки с полом, номер и кнопки не трогаются', () => {
  const widths = columnWidths(COLUMNS, 620)

  assert.equal(widths.id, 100)
  assert.equal(widths.actions, 130)
  assert.ok(widths.address < 180 && widths.address >= 120)
  assert.ok(widths.coordinates < 140 && widths.coordinates >= 90)
  assert.ok(total(widths) <= 620)
})

test('совсем узкое окно: всё ужимается пропорционально, но в таблицу помещается', () => {
  const widths = columnWidths(COLUMNS, 400)

  assert.ok(widths.id < 100)
  assert.ok(total(widths) <= 400)
})

test('пока ширина неизвестна — удобная раскладка', () => {
  const widths = columnWidths(COLUMNS, 0)

  assert.equal(widths.address, 180)
  assert.equal(widths.coordinates, 140)
})

test('совсем узкое окно: колонка с кнопками (fixed) своей ширины, ужимаются остальные', () => {
  const columns = COLUMNS.map((column) => (column.key === 'actions' ? { ...column, fixed: true } : column))
  const widths = columnWidths(columns, 400)

  assert.equal(widths.actions, 130)
  assert.ok(widths.id < 100)
  assert.ok(total(widths) <= 400)
})
