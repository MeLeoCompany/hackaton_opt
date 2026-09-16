// Что диспетчер видит из списка заявок: фильтры -> сортировка -> страница, и выбранная заявка.
// Данные не меняет — только показывает. Загрузка и сохранение живут в useRequestsTable.

import { computed, reactive, ref, watch } from 'vue'

import { moscowTimeOf } from '../utils/moscowTime.js'
import { referenceName } from '../utils/referenceNames.js'

// значение фильтра транспорта «транспорт не важен» (в заявке transport_id = null)
export const NO_TRANSPORT = 'none'

export const PAGE_SIZES = [10, 25, 50, 100]

// '' — сортировка не выбрана: строки идут в порядке бэкенда
const DEFAULT_SORT = ''

// sortKey: null — по колонке не сортируем; key — какой фильтр стоит под колонкой;
// width — фиксированная ширина, чтобы колонки не прыгали при фильтрации и правке строки
export const REQUEST_COLUMNS = [
  { key: 'id', label: '№', sortKey: 'id', width: '90px' },
  { key: 'is_active', label: 'Активна', sortKey: 'is_active', width: '110px' },
  { key: 'address', label: 'Адрес', sortKey: 'address', width: '' },
  { key: 'coordinates', label: 'Координаты', sortKey: null, width: '140px' },
  { key: 'work_type', label: 'Тип работ', sortKey: 'work_type', width: '320px' },
  { key: 'duration', label: 'Работа, мин', sortKey: 'duration_minutes', width: '110px' },
  { key: 'window', label: 'Окно (МСК)', sortKey: 'window_start', width: '130px' },
  { key: 'priority', label: 'Приоритет', sortKey: 'priority', width: '130px' },
  { key: 'transport', label: 'Транспорт', sortKey: 'transport', width: '190px' },
  { key: 'actions', label: '', sortKey: null, width: '130px' },
]

// по фильтру на каждую колонку таблицы
function emptyFilters() {
  return {
    idText: '', // часть номера заявки
    activity: '', // '' — все, 'active' — только активные, 'inactive' — только выключенные
    text: '', // часть адреса
    coordinates: '', // часть координат, как они показаны в таблице
    workTypeId: '', // '' — любой тип работ
    durationFrom: '', // минуты работы на месте, не меньше
    durationTo: '', // минуты работы на месте, не больше
    timeFrom: '', // 'HH:MM' — окно начинается не раньше
    timeTo: '', // 'HH:MM' — окно начинается не позже
    priorityId: '', // '' — любой
    transportId: '', // '' — любой, NO_TRANSPORT — «не важен», иначе номер транспорта
  }
}

export function useRequestsView(requests, references) {
  const filters = reactive(emptyFilters())
  const sortKey = ref(DEFAULT_SORT)
  const sortDirection = ref('asc')
  const page = ref(1)
  const pageSize = ref(25)
  const selectedId = ref(null)

  // ---- фильтры ----

  const activeFilterCount = computed(
    () => Object.entries(emptyFilters()).filter(([name, emptyValue]) => filters[name] !== emptyValue).length,
  )

  function matchesFilters(request) {
    if (filters.activity === 'active' && !request.is_active) return false
    if (filters.activity === 'inactive' && request.is_active) return false

    if (filters.idText && !String(request.id).includes(filters.idText.trim())) return false

    const query = filters.text.trim().toLowerCase()
    if (query && !request.address.toLowerCase().includes(query)) return false

    const coordinates = filters.coordinates.trim().replace(',', '').toLowerCase()
    if (coordinates && !`${request.latitude.toFixed(4)} ${request.longitude.toFixed(4)}`.includes(coordinates)) {
      return false
    }

    if (filters.durationFrom !== '' && request.duration_minutes < Number(filters.durationFrom)) return false
    if (filters.durationTo !== '' && request.duration_minutes > Number(filters.durationTo)) return false

    if (filters.priorityId !== '' && request.priority_id !== filters.priorityId) return false
    if (filters.workTypeId !== '' && request.work_type_id !== filters.workTypeId) return false

    if (filters.transportId === NO_TRANSPORT) {
      if (request.transport_id !== null) return false
    } else if (filters.transportId !== '' && request.transport_id !== filters.transportId) {
      return false
    }

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

  // без выбранной сортировки — порядок, в котором заявки пришли с бэкенда: по началу окна
  const sortedRequests = computed(() =>
    sortKey.value ? [...filteredRequests.value].sort(compareRequests) : filteredRequests.value,
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
