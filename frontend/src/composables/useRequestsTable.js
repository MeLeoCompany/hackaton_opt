// Заявки: загрузка, добавление, изменение, удаление, включение/выключение.
// Фильтры, сортировка и страницы — в useRequestsView, загрузка из CSV — в useRequestsImport.

import { ref, watch } from 'vue'

import { fetchReferences } from '../api/referencesApi.js'
import {
  createRequest,
  deleteRequest,
  exportRequestsCsv,
  importRequestsCsv,
  listRequests,
  setRequestsActive,
  updateRequest,
} from '../api/requestsApi.js'
import { downloadBlob } from '../utils/downloadFile.js'
import { fromMoscowInputValue, toMoscowInputValue } from '../utils/moscowTime.js'
import { useMessages } from './useMessages.js'
import { useSelectedDay } from './useSelectedDay.js'

export const NEW_REQUEST = 'new'

export function useRequestsTable() {
  const { selectedDay, refreshDaysWithRequests } = useSelectedDay()
  const requests = ref([])
  const references = ref({ skills: [], priorities: [], transports: [], work_types: [] })

  const loading = ref(false)
  const saving = ref(false)
  const { errorMessage, errorDetails, noticeMessage, showError, showNotice, clearMessages } = useMessages()

  // какая строка сейчас редактируется: номер заявки, NEW_REQUEST для новой или null
  const editingId = ref(null)
  // значения полей формы — в том виде, в каком их отдают поля ввода
  const form = ref(null)
  let loadRequest = 0

  async function load() {
    const request = ++loadRequest
    const day = selectedDay.value
    loading.value = true
    clearMessages()
    try {
      const [loadedReferences, loadedRequests] = await Promise.all([
        fetchReferences(),
        listRequests(day),
      ])
      if (request !== loadRequest) return
      references.value = loadedReferences
      requests.value = loadedRequests
    } catch (error) {
      if (request === loadRequest) showError(error)
    } finally {
      if (request === loadRequest) loading.value = false
    }
  }

  function startCreate() {
    clearMessages()
    editingId.value = NEW_REQUEST
    form.value = {
      id: '',
      address: '',
      latitude: '',
      longitude: '',
      duration_minutes: references.value.work_types[0]?.work_minutes ?? 60,
      window_start: '',
      window_end: '',
      priority_id: references.value.priorities[0]?.id ?? '',
      skill_id: references.value.work_types[0]?.skill_id ?? '',
      transport_id: '',
      work_type_id: references.value.work_types[0]?.id ?? '',
      is_active: true,
    }
  }

  // выбрали тип работ — подставляем норматив работы на месте и нужный навык:
  // навык отдельно не выбирают, он определяется типом работ
  function applyWorkTypeNorms(workTypeId) {
    const workType = references.value.work_types.find((item) => item.id === Number(workTypeId))
    if (!workType) return
    form.value.duration_minutes = workType.work_minutes
    form.value.skill_id = workType.skill_id
  }

  function startEdit(request) {
    clearMessages()
    editingId.value = request.id
    form.value = {
      id: request.id,
      address: request.address,
      latitude: request.latitude,
      longitude: request.longitude,
      duration_minutes: request.duration_minutes,
      window_start: toMoscowInputValue(request.window_start),
      window_end: toMoscowInputValue(request.window_end),
      priority_id: request.priority_id,
      skill_id: request.skill_id,
      transport_id: request.transport_id ?? '',
      work_type_id: request.work_type_id ?? '',
      is_active: request.is_active,
    }
  }

  function cancelEdit() {
    editingId.value = null
    form.value = null
  }

  // пустое поле ввода -> null, чтобы бэкенд ответил «не заполнено», а не «не число»
  function numberOrNull(value) {
    return value === '' || value === null || value === undefined ? null : Number(value)
  }

  function formToPayload() {
    const values = form.value
    return {
      address: values.address.trim(),
      latitude: numberOrNull(values.latitude),
      longitude: numberOrNull(values.longitude),
      duration_minutes: numberOrNull(values.duration_minutes),
      window_start: values.window_start ? fromMoscowInputValue(values.window_start) : null,
      window_end: values.window_end ? fromMoscowInputValue(values.window_end) : null,
      priority_id: numberOrNull(values.priority_id),
      skill_id: numberOrNull(values.skill_id),
      transport_id: numberOrNull(values.transport_id),
      work_type_id: numberOrNull(values.work_type_id),
      is_active: values.is_active,
    }
  }

  async function saveForm() {
    saving.value = true
    clearMessages()
    try {
      const payload = formToPayload()
      let notice
      if (editingId.value === NEW_REQUEST) {
        const created = await createRequest({ ...payload, id: numberOrNull(form.value.id) })
        notice = `Заявка №${created.id} добавлена`
      } else {
        await updateRequest(editingId.value, payload)
        notice = `Заявка №${editingId.value} сохранена`
      }
      cancelEdit()
      await Promise.all([load(), refreshDaysWithRequests()])
      showNotice(notice)
    } catch (error) {
      showError(error)
    } finally {
      saving.value = false
    }
  }

  async function remove(request) {
    if (!window.confirm(`Удалить заявку №${request.id}?`)) return
    clearMessages()
    try {
      await deleteRequest(request.id)
      requests.value = requests.value.filter((item) => item.id !== request.id)
      await refreshDaysWithRequests()
      showNotice(`Заявка №${request.id} удалена`)
    } catch (error) {
      showError(error)
    }
  }

  // включить или выключить заявки для планирования.
  // Заменяем объекты заявок целиком, чтобы отфильтрованный список и карта пересчитались.
  async function setActive(requestIds, isActive) {
    clearMessages()
    try {
      await setRequestsActive(requestIds, isActive)
      const changedIds = new Set(requestIds)
      requests.value = requests.value.map((request) =>
        changedIds.has(request.id) ? { ...request, is_active: isActive } : request,
      )
      await refreshDaysWithRequests()
      if (requestIds.length === 1) {
        showNotice(`Заявка №${requestIds[0]} ${isActive ? 'включена' : 'выключена'}`)
      } else {
        showNotice(`${isActive ? 'Включено' : 'Выключено'} заявок: ${requestIds.length}`)
      }
    } catch (error) {
      showError(error)
    }
  }

  // ---- слепок дня ----

  async function exportDay() {
    clearMessages()
    try {
      downloadBlob(await exportRequestsCsv(selectedDay.value), `requests_${selectedDay.value}.csv`)
    } catch (error) {
      showError(error)
    }
  }

  // Файл кладётся в выбранный день копией: время суток то же, номера новые.
  // Существующие заявки дня не трогаем: они могут быть в планах, и их удаление
  // либо сломало бы план, либо упёрлось в запрет удаления. Поэтому только предупреждаем.
  async function importDay(file) {
    if (requests.value.length) {
      const confirmed = window.confirm(
        `На этот день уже есть заявок: ${requests.value.length}. ` +
          `Из файла «${file.name}» они добавятся копиями, существующие останутся. Продолжить?`,
      )
      if (!confirmed) return
    }
    saving.value = true
    clearMessages()
    try {
      const report = await importRequestsCsv(file, selectedDay.value)
      await load()
      showNotice(
        `В день ${selectedDay.value} добавлено заявок: ${report.created}` +
          (report.updated ? `, обновлено ${report.updated}` : ''),
      )
    } catch (error) {
      showError(error)
    } finally {
      saving.value = false
    }
  }

  // сменили день — таблица перезагружается на новый день
  watch(selectedDay, () => {
    cancelEdit()
    load()
  })

  return {
    requests,
    references,
    applyWorkTypeNorms,
    exportDay,
    importDay,
    loading,
    saving,
    errorMessage,
    errorDetails,
    noticeMessage,
    editingId,
    form,
    load,
    startCreate,
    startEdit,
    cancelEdit,
    saveForm,
    remove,
    setActive,
  }
}
