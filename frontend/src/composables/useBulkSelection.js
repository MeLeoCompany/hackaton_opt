// Галочки в таблице: выбранные строки живут номерами, поэтому выбор переживает и
// перелистывание страниц, и перерисовку таблицы. Shift-клик отмечает всё от прошлой
// галочки до этой — так десяток соседних строк выбирается одним движением.

import { computed, ref } from 'vue'

export function useBulkSelection(visibleRows) {
  const selected = ref(new Set())
  // строка, с которой начинается диапазон для Shift-клика
  let anchorId = null

  const visibleIds = computed(() => visibleRows().map((row) => row.id))
  const selectedIds = computed(() => [...selected.value])
  const count = computed(() => selected.value.size)
  const allVisibleSelected = computed(
    () => visibleIds.value.length > 0 && visibleIds.value.every((id) => selected.value.has(id)),
  )
  const someVisibleSelected = computed(
    () => !allVisibleSelected.value && visibleIds.value.some((id) => selected.value.has(id)),
  )

  function change(apply) {
    const next = new Set(selected.value)
    apply(next)
    selected.value = next
  }

  function isSelected(id) {
    return selected.value.has(id)
  }

  function toggleRow(id, withShift = false) {
    const ids = visibleIds.value
    const from = ids.indexOf(anchorId)
    const to = ids.indexOf(id)
    if (withShift && from !== -1 && to !== -1) {
      const [start, end] = from < to ? [from, to] : [to, from]
      const range = ids.slice(start, end + 1)
      const add = !selected.value.has(id)
      change((next) => range.forEach((rowId) => (add ? next.add(rowId) : next.delete(rowId))))
    } else {
      change((next) => (next.has(id) ? next.delete(id) : next.add(id)))
    }
    anchorId = id
  }

  // галочка в шапке: снимаем, если на странице уже выбрано всё, иначе добираем остальные
  function toggleVisible() {
    const ids = visibleIds.value
    const clearing = allVisibleSelected.value
    change((next) => ids.forEach((id) => (clearing ? next.delete(id) : next.add(id))))
    anchorId = null
  }

  function clear() {
    selected.value = new Set()
    anchorId = null
  }

  // строк могло не стать: сменили день, удалили записи — такие номера из выбора уходят
  function keepOnly(ids) {
    const alive = new Set(ids)
    change((next) => [...next].forEach((id) => alive.has(id) || next.delete(id)))
  }

  return {
    selectedIds,
    count,
    isSelected,
    toggleRow,
    toggleVisible,
    allVisibleSelected,
    someVisibleSelected,
    clear,
    keepOnly,
  }
}
