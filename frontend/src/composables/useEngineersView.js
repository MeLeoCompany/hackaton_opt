// Что диспетчер видит из списка исполнителей: фильтры -> сортировка, и выбранный исполнитель.
// Данные не меняет — только показывает. Страниц нет: исполнителей по ТЗ 10-15.

import { computed, reactive, ref, watch } from 'vue'

import { moscowTimeOf } from '../utils/moscowTime.js'
import { referenceName } from '../utils/referenceNames.js'

// sortKey: null — по колонке не сортируем; key — какой фильтр стоит под колонкой;
// width — фиксированная ширина, чтобы колонки не прыгали при фильтрации и правке строки
export const ENGINEER_COLUMNS = [
  { key: 'id', label: '№', sortKey: 'id', width: '90px' },
  { key: 'name', label: 'Имя', sortKey: 'name', width: '260px' },
  { key: 'transport', label: 'Транспорт', sortKey: 'transport', width: '220px' },
  { key: 'skills', label: 'Навыки', sortKey: 'skills', width: '' },
  { key: 'shift', label: 'Смена (МСК)', sortKey: 'shift_start', width: '130px' },
  { key: 'start', label: 'Старт', sortKey: null, width: '150px' },
  { key: 'actions', label: '', sortKey: null, width: '130px' },
]

// '' — сортировка не выбрана: строки идут в порядке бэкенда
const DEFAULT_SORT = ''

// по фильтру на каждую колонку таблицы
function emptyFilters() {
  return {
    idText: '', // часть номера исполнителя
    text: '', // часть имени
    transportId: '', // '' — любой
    skillId: '', // '' — любой; иначе исполнитель должен уметь этот навык
    shiftFrom: '', // 'HH:MM' — смена начинается не раньше
    shiftTo: '', // 'HH:MM' — смена начинается не позже
    startText: '', // часть координат старта, как они показаны в таблице
  }
}

export function useEngineersView(engineers, references) {
  const filters = reactive(emptyFilters())
  const sortKey = ref(DEFAULT_SORT)
  const sortDirection = ref('asc')
  const selectedId = ref(null)

  const activeFilterCount = computed(
    () => Object.entries(emptyFilters()).filter(([name, emptyValue]) => filters[name] !== emptyValue).length,
  )

  function matchesFilters(engineer) {
    if (filters.idText && !String(engineer.id).includes(filters.idText.trim())) return false

    const query = filters.text.trim().toLowerCase()
    if (query && !engineer.name.toLowerCase().includes(query)) return false

    if (filters.transportId !== '' && engineer.transport_id !== filters.transportId) return false
    if (filters.skillId !== '' && !engineer.skill_ids.includes(filters.skillId)) return false

    const shiftStart = moscowTimeOf(engineer.shift_start)
    if (filters.shiftFrom && shiftStart < filters.shiftFrom) return false
    if (filters.shiftTo && shiftStart > filters.shiftTo) return false

    const start = filters.startText.trim().replace(',', '').toLowerCase()
    if (
      start &&
      !`${engineer.start_latitude.toFixed(4)} ${engineer.start_longitude.toFixed(4)}`.includes(start)
    ) {
      return false
    }

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

  // без выбранной сортировки — порядок бэкенда: в каком порядке исполнителей заводили
  const sortedEngineers = computed(() =>
    sortKey.value ? [...filteredEngineers.value].sort(compareEngineers) : filteredEngineers.value,
  )

  // клик по заголовку по кругу: по возрастанию -> по убыванию -> как по умолчанию.
  // Другая колонка всегда начинает с возрастания.
  function toggleSort(key) {
    if (sortKey.value !== key) {
      sortKey.value = key
      sortDirection.value = 'asc'
    } else if (sortDirection.value === 'asc') {
      sortDirection.value = 'desc'
    } else {
      sortKey.value = DEFAULT_SORT
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
