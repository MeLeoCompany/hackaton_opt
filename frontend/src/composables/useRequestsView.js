// Что диспетчер видит из списка заявок: фильтры -> сортировка -> страница, и выбранная заявка.
// Данные не меняет — только показывает. Загрузка и сохранение живут в useRequestsTable.

import { computed, reactive, ref, watch } from 'vue'

import { moscowDateOf, moscowTimeOf } from '../utils/moscowTime.js'
import { referenceName } from '../utils/referenceNames.js'

// значение фильтра транспорта «транспорт не важен» (в заявке transport_id = null)
export const NO_TRANSPORT = 'none'

export const PAGE_SIZES = [10, 25, 50, 100]

function emptyFilters() {
  return {
    activity: '', // '' — все, 'active' — только активные, 'inactive' — только выключенные
    text: '', // часть номера или адреса
    priorityId: '', // '' — любой
    workTypeId: '', // '' — любой тип работ
    transportId: '', // '' — любой, NO_TRANSPORT — «не важен», иначе номер транспорта
    day: '', // 'YYYY-MM-DD' — московская дата начала окна
    timeFrom: '', // 'HH:MM' — окно начинается не раньше
    timeTo: '', // 'HH:MM' — окно начинается не позже
  }
}

export function useRequestsView(requests, references) {
  const filters = reactive(emptyFilters())
  const sortKey = ref('window_start')
  const sortDirection = ref('asc')
  const page = ref(1)
  const pageSize = ref(25)
  const selectedId = ref(null)

  // ---- фильтры ----

  const availableDays = computed(() => {
    const days = new Set(requests.value.map((request) => moscowDateOf(request.window_start)))
    return [...days].sort()
  })

  const activeFilterCount = computed(
    () => Object.entries(emptyFilters()).filter(([name, emptyValue]) => filters[name] !== emptyValue).length,
  )

  function matchesFilters(request) {
    if (filters.activity === 'active' && !request.is_active) return false
    if (filters.activity === 'inactive' && request.is_active) return false

    const query = filters.text.trim().toLowerCase()
    if (query && !String(request.id).includes(query) && !request.address.toLowerCase().includes(query)) {
      return false
    }
    if (filters.priorityId !== '' && request.priority_id !== filters.priorityId) return false
    if (filters.workTypeId !== '' && request.work_type_id !== filters.workTypeId) return false

    if (filters.transportId === NO_TRANSPORT) {
      if (request.transport_id !== null) return false
    } else if (filters.transportId !== '' && request.transport_id !== filters.transportId) {
      return false
    }

    if (filters.day && moscowDateOf(request.window_start) !== filters.day) return false

    const windowStartTime = moscowTimeOf(request.window_start)
    if (filters.timeFrom && windowStartTime < filters.timeFrom) return false
    if (filters.timeTo && windowStartTime > filters.timeTo) return false

    return true
  }

  const filteredRequests = computed(() => requests.value.filter(matchesFilters))

  function resetFilters() {
    Object.assign(filters, emptyFilters())
  }

  // ---- сортировка ----

  function sortValue(request) {
    switch (sortKey.value) {
      case 'id':
        return request.id
      case 'is_active':
        return request.is_active ? 0 : 1 // по возрастанию — сначала активные
      case 'address':
        return request.address
      case 'duration_minutes':
        return request.duration_minutes
      case 'window_start':
        return new Date(request.window_start).getTime()
      case 'priority':
        return referenceName(references.value, 'priorities', request.priority_id)
      case 'work_type':
        return request.work_type_id === null ? null : referenceName(references.value, 'work_types', request.work_type_id)
      case 'transport':
        return request.transport_id === null ? null : referenceName(references.value, 'transports', request.transport_id)
      default:
        return null
    }
  }

  function compareRequests(first, second) {
    const firstValue = sortValue(first)
    const secondValue = sortValue(second)

    // пустое значение (транспорт «не важен») всегда внизу, в какую сторону ни сортируй
    if (firstValue === null && secondValue !== null) return 1
    if (secondValue === null && firstValue !== null) return -1

    let result = 0
    if (typeof firstValue === 'string') result = firstValue.localeCompare(secondValue, 'ru')
    else if (firstValue !== null) result = firstValue - secondValue

    if (result !== 0) return sortDirection.value === 'asc' ? result : -result
    // одинаковые значения — по номеру заявки, чтобы строки не перескакивали местами
    return first.id - second.id
  }

  const sortedRequests = computed(() => [...filteredRequests.value].sort(compareRequests))

  // клик по заголовку: та же колонка — меняем направление, другая — сортируем по ней по возрастанию
  function toggleSort(key) {
    if (sortKey.value === key) {
      sortDirection.value = sortDirection.value === 'asc' ? 'desc' : 'asc'
    } else {
      sortKey.value = key
      sortDirection.value = 'asc'
    }
  }

  // ---- страницы ----

  const pageCount = computed(() => Math.max(1, Math.ceil(sortedRequests.value.length / pageSize.value)))
  // если после удаления или фильтра страниц стало меньше — остаёмся на последней существующей
  const currentPage = computed(() => Math.min(page.value, pageCount.value))

  const pageRequests = computed(() => {
    const firstIndex = (currentPage.value - 1) * pageSize.value
    return sortedRequests.value.slice(firstIndex, firstIndex + pageSize.value)
  })

  // поменялись фильтры, сортировка или размер страницы — возвращаемся на первую страницу
  watch([filters, sortKey, sortDirection, pageSize], () => {
    page.value = 1
  }, { deep: true })

  // ---- выбранная заявка ----

  // выбрать заявку (например, кликом по точке на карте) и перелистнуть на её страницу
  function selectRequest(requestId) {
    selectedId.value = requestId
    const index = sortedRequests.value.findIndex((request) => request.id === requestId)
    if (index >= 0) page.value = Math.floor(index / pageSize.value) + 1
  }

  // выбранная заявка пропала из выборки (фильтр, удаление) — снимаем выделение
  watch(filteredRequests, (visibleRequests) => {
    if (selectedId.value !== null && !visibleRequests.some((request) => request.id === selectedId.value)) {
      selectedId.value = null
    }
  })

  return {
    filters,
    availableDays,
    activeFilterCount,
    filteredRequests,
    resetFilters,
    sortKey,
    sortDirection,
    toggleSort,
    page,
    pageSize,
    pageCount,
    currentPage,
    pageRequests,
    selectedId,
    selectRequest,
  }
}
