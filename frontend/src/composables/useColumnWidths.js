// Ширины колонок таблиц заявок и исполнителей — от фактической ширины таблицы.
//
// Колонки двух видов:
//   - компактные (width: '100px') — номер, время, кнопки: своей ширины;
//   - растущие (grow, minWidth) — адрес, тип работ, транспорт, навыки: текст в них
//     переносится по словам, они забирают остаток ширины по весам grow.
// У любой колонки может быть floor — до какой ширины её можно сузить, не обрезая
// содержимое (координаты уходят в две строки, адрес и тип работ — в несколько).
// fixed: true — колонка не сужается никогда (кнопки правки и удаления: они той же ширины,
// что кнопки полос над таблицей, и не должны мельчать при раскрытом меню).
// Сжатие окна идёт по ступеням:
//   1. хватает места на всё — компактные своей ширины, растущие делят остаток;
//   2. не хватает — колонки с floor сужаются к своему полу, каждая по своему запасу;
//   3. не хватает даже полов — всё ужимается пропорционально, ячейки обрезают лишнее
//      многоточием (класс fluid в common.css). Прокрутки нет ни на одной ступени.
// Ширины зависят только от ширины таблицы, поэтому колонки не прыгают при фильтрации.

import { computed, onBeforeUnmount, ref, watch } from 'vue'

function preferred(column) {
  return column.grow ? column.minWidth : parseInt(column.width, 10)
}

function floorOf(column) {
  return column.floor ?? preferred(column)
}

// чистая функция: ширины колонок { key: px } для доступной ширины таблицы
export function columnWidths(columns, available) {
  const comfortable = columns.reduce((sum, column) => sum + preferred(column), 0)
  const floors = columns.reduce((sum, column) => sum + floorOf(column), 0)
  const growTotal = columns.reduce((sum, column) => sum + (column.grow ?? 0), 0)
  const width = available > 0 ? available : comfortable

  const result = {}
  if (width >= comfortable) {
    const extra = width - comfortable
    for (const column of columns) {
      const grown = column.grow ? (extra * column.grow) / growTotal : 0
      result[column.key] = Math.floor(preferred(column) + grown)
    }
  } else if (width >= floors) {
    const deficit = comfortable - width
    const slack = comfortable - floors
    for (const column of columns) {
      const own = preferred(column) - floorOf(column)
      result[column.key] = Math.floor(preferred(column) - (deficit * own) / slack)
    }
  } else {
    // ужимаются все, кроме fixed: те своей ширины, остальные делят оставшееся
    const fixedTotal = columns.reduce((sum, column) => sum + (column.fixed ? floorOf(column) : 0), 0)
    const scale = Math.max(width - fixedTotal, 0) / (floors - fixedTotal)
    for (const column of columns) {
      result[column.key] = column.fixed ? floorOf(column) : Math.floor(floorOf(column) * scale)
    }
  }
  return result
}

// ширины колонок для таблицы внутри container (ref на элемент с таблицей во всю ширину)
export function useColumnWidths(columns, container) {
  const available = ref(0)
  const observer = new ResizeObserver(([entry]) => {
    available.value = entry.contentRect.width
  })

  watch(
    container,
    (element, previous) => {
      if (previous) observer.unobserve(previous)
      if (element) observer.observe(element)
    },
    { immediate: true },
  )
  onBeforeUnmount(() => observer.disconnect())

  const widths = computed(() => columnWidths(columns, available.value))
  return { widths }
}
