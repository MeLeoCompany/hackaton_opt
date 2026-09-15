// Что диспетчер видит из списка исполнителей: фильтры -> сортировка, и выбранный исполнитель.
// Данные не меняет — только показывает. Страниц нет: исполнителей по ТЗ 10-15.

import { computed, reactive, ref, watch } from 'vue'

import { referenceName } from '../utils/referenceNames.js'

function emptyFilters() {
  return {
    text: '', // часть имени или номера
    transportId: '', // '' — любой
    skillId: '', // '' — любой; иначе исполнитель должен уметь этот навык
  }
}

export function useEngineersView(engineers, references) {
  const filters = reactive(emptyFilters())
  const sortKey = ref('name')
  const sortDirection = ref('asc')
  const selectedId = ref(null)

  const activeFilterCount = computed(
    () => Object.entries(emptyFilters()).filter(([name, emptyValue]) => filters[name] !== emptyValue).length,
  )

  function matchesFilters(engineer) {
    const query = filters.text.trim().toLowerCase()
    if (query && !String(engineer.id).includes(query) && !engineer.name.toLowerCase().includes(query)) {
      return false
    }
    if (filters.transportId !== '' && engineer.transport_id !== filters.transportId) return false
    if (filters.skillId !== '' && !engineer.skill_ids.includes(filters.skillId)) return false
    return true
  }

  const filteredEngineers = computed(() => engineers.value.filter(matchesFilters))

  function resetFilters() {
    Object.assign(filters, emptyFilters())
  }

  function sortValue(engineer) {
    switch (sortKey.value) {
      case 'id':
        return engineer.id
      case 'name':
        return engineer.name
      case 'transport':
        return referenceName(references.value, 'transports', engineer.transport_id)
      case 'skills':
        return engineer.skill_ids.length
      case 'shift_start':
        return new Date(engineer.shift_start).getTime()
      default:
        return null
    }
  }

  function compareEngineers(first, second) {
    const firstValue = sortValue(first)
    const secondValue = sortValue(second)
    const result =
      typeof firstValue === 'string' ? firstValue.localeCompare(secondValue, 'ru') : firstValue - secondValue
    if (result !== 0) return sortDirection.value === 'asc' ? result : -result
    // одинаковые значения — по номеру, чтобы строки не перескакивали местами
    return first.id - second.id
  }

  const sortedEngineers = computed(() => [...filteredEngineers.value].sort(compareEngineers))

  // клик по заголовку: та же колонка — меняем направление, другая — сортируем по ней по возрастанию
  function toggleSort(key) {
    if (sortKey.value === key) {
      sortDirection.value = sortDirection.value === 'asc' ? 'desc' : 'asc'
    } else {
      sortKey.value = key
      sortDirection.value = 'asc'
    }
  }

  // выбранный исполнитель пропал из выборки (фильтр, удаление) — снимаем выделение
  watch(filteredEngineers, (visibleEngineers) => {
    if (selectedId.value !== null && !visibleEngineers.some((engineer) => engineer.id === selectedId.value)) {
      selectedId.value = null
    }
  })

  return {
    filters,
    activeFilterCount,
    filteredEngineers,
    sortedEngineers,
    resetFilters,
    sortKey,
    sortDirection,
    toggleSort,
    selectedId,
  }
}
