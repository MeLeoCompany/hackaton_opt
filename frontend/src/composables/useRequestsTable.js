// Заявки: загрузка, добавление, изменение, удаление, включение/выключение, загрузка из CSV.
// Фильтры, сортировка и страницы — в useRequestsView.

import { ref } from 'vue'

import { fetchReferences } from '../api/referencesApi.js'
import {
  createRequest,
  deleteRequest,
  downloadCsvTemplate,
  importRequestsCsv,
  listRequests,
  setRequestsActive,
  updateRequest,
} from '../api/requestsApi.js'
import { fromMoscowInputValue, toMoscowInputValue } from '../utils/moscowTime.js'
import { useMessages } from './useMessages.js'

export const NEW_REQUEST = 'new'

export function useRequestsTable() {
  const requests = ref([])
  const references = ref({ skills: [], priorities: [], transports: [] })

  const loading = ref(false)
  const saving = ref(false)
  const { errorMessage, errorDetails, noticeMessage, showError, showNotice, clearMessages } = useMessages()

  // какая строка сейчас редактируется: номер заявки, NEW_REQUEST для новой или null
  const editingId = ref(null)
  // значения полей формы — в том виде, в каком их отдают поля ввода
  const form = ref(null)

  async function load() {
    loading.value = true
    clearMessages()
    try {
      const [loadedReferences, loadedRequests] = await Promise.all([fetchReferences(), listRequests()])
      references.value = loadedReferences
      requests.value = loadedRequests
    } catch (error) {
      showError(error)
    } finally {
      loading.value = false
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
      duration_minutes: 60,
      window_start: '',
      window_end: '',
      priority_id: references.value.priorities[0]?.id ?? '',
      skill_id: references.value.skills[0]?.id ?? '',
      transport_id: '',
      is_active: true,
    }
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
      is_active: values.is_active,
    }
  }

  async function saveForm() {
    saving.value = true
    clearMessages()
    try {
      const payload = formToPayload()
      if (editingId.value === NEW_REQUEST) {
        const created = await createRequest({ ...payload, id: numberOrNull(form.value.id) })
        showNotice(`Заявка №${created.id} добавлена`)
      } else {
        await updateRequest(editingId.value, payload)
        showNotice(`Заявка №${editingId.value} сохранена`)
      }
      cancelEdit()
      requests.value = await listRequests()
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
      if (requestIds.length === 1) {
        showNotice(`Заявка №${requestIds[0]} ${isActive ? 'включена' : 'выключена'}`)
      } else {
        showNotice(`${isActive ? 'Включено' : 'Выключено'} заявок: ${requestIds.length}`)
      }
    } catch (error) {
      showError(error)
    }
  }

  async function importCsv(file) {
    saving.value = true
    clearMessages()
    try {
      const report = await importRequestsCsv(file)
      requests.value = await listRequests()
      showNotice(`Файл «${file.name}» загружен: добавлено ${report.created}, обновлено ${report.updated}`)
    } catch (error) {
      showError(error)
    } finally {
      saving.value = false
    }
  }

  async function downloadTemplate() {
    try {
      const blob = await downloadCsvTemplate()
      const link = document.createElement('a')
      link.href = URL.createObjectURL(blob)
      link.download = 'requests_template.csv'
      link.click()
      setTimeout(() => URL.revokeObjectURL(link.href), 1000)
    } catch (error) {
      showError(error)
    }
  }

  return {
    requests,
    references,
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
    importCsv,
    downloadTemplate,
  }
}
