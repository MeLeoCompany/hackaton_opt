// Что диспетчер видит из списка исполнителей: фильтры -> сортировка, и выбранный исполнитель.
// Данные не меняет — только показывает. Страниц нет: исполнителей по ТЗ 10-15.

import { computed, reactive, ref, watch } from 'vue'

import { moscowTimeOf } from '../utils/moscowTime.js'
import { referenceName } from '../utils/referenceNames.js'

// sortKey: null — по колонке не сортируем; key — какой фильтр стоит под колонкой;
// width — фиксированная ширина, чтобы колонки не прыгали при фильтрации и правке строки
export const ENGINEER_COLUMNS = [
  // галочки: отмеченные строки меняют и удаляют группой
  { key: 'select', label: '', sortKey: null, width: '40px', fixed: true },
  { key: 'id', label: '№', sortKey: 'id', width: '90px' },
  { key: 'name', label: 'Бригада', sortKey: 'name', grow: 1, minWidth: 170, floor: 130 },
  { key: 'transport', label: 'Транспорт', sortKey: 'transport', width: '215px', floor: 170 },
  { key: 'skills', label: 'Навыки', sortKey: 'skills', grow: 2, minWidth: 230, floor: 170 },
  // что бригада везёт с собой: тип и количество, отдельно от навыков
  { key: 'equipment', label: 'Оборудование', sortKey: null, grow: 1, minWidth: 160, floor: 130 },
  { key: 'shift', label: 'Смена (МСК)', sortKey: 'shift_start', width: '130px' },
  // откуда выезжает: значок офиса или своей точки; в правке по значку открывается карта
  { key: 'start', label: 'Старт', sortKey: null, width: '72px' },
  // кнопки правки и удаления не сужаются — как у заявок
  { key: 'actions', label: '', sortKey: null, width: '130px', fixed: true },
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
    equipmentId: '', // '' — неважно, иначе номер оборудования, которое бригада везёт
    shiftFrom: '', // 'HH:MM' — смена начинается не раньше
    shiftTo: '', // 'HH:MM' — смена начинается не позже
    startKind: '', // '' — любой старт, 'office' — из офиса, 'own' — из своей точки
  }
}

export function useEngineersView(engineers, references, pinnedId = ref(null)) {
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

    const carried = (engineer.equipment ?? []).map((item) => item.equipment_id)
    if (filters.equipmentId !== '' && !carried.includes(filters.equipmentId)) {
      return false
    }

    if (filters.startKind === 'office' && !engineer.start_at_office) return false
    if (filters.startKind === 'own' && engineer.start_at_office) return false

    const shiftStart = moscowTimeOf(engineer.shift_start)
    if (filters.shiftFrom && shiftStart < filters.shiftFrom) return false
    if (filters.shiftTo && shiftStart > filters.shiftTo) return false


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
  const sortedEngineers = computed(() => {
    const sorted = sortKey.value ? [...filteredEngineers.value].sort(compareEngineers) : filteredEngineers.value
    // только что добавленная — первой строкой, пока не выбрали другую сортировку
    const pinned = sorted.find((engineer) => engineer.id === pinnedId.value)
    return pinned ? [pinned, ...sorted.filter((engineer) => engineer !== pinned)] : sorted
  })

  // клик по заголовку по кругу: по возрастанию -> по убыванию -> как по умолчанию.
  // Другая колонка всегда начинает с возрастания.
  function toggleSort(key) {
    pinnedId.value = null
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
