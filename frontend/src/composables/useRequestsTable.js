// Заявки: загрузка, добавление, изменение, удаление, смена статуса.
// Фильтры, сортировка и страницы — в useRequestsView, загрузка из CSV — в useRequestsImport.

import { ref, watch } from 'vue'

import { fetchReferences } from '../api/referencesApi.js'
import {
  createRequest,
  deleteRequest,
  duplicateRequest,
  exportRequestsCsv,
  importRequestsCsv,
  listRequests,
  setRequestsStatus,
  updateRequest,
} from '../api/requestsApi.js'
import { downloadBlob } from '../utils/downloadFile.js'
import { formatDay, fromMoscowInputValue, toMoscowInputValue } from '../utils/moscowTime.js'
import { useMessages } from './useMessages.js'
import { useSelectedDay } from './useSelectedDay.js'
import { equipmentPayload } from '../utils/equipment.js'
import { referenceName } from '../utils/referenceNames.js'

export const NEW_REQUEST = 'new'

export function useRequestsTable() {
  const { selectedDay, refreshDaysWithRequests } = useSelectedDay()
  const requests = ref([])
  const references = ref({ skills: [], priorities: [], transports: [], work_types: [], offices: [], equipment: [] })

  const loading = ref(false)
  const saving = ref(false)
  // только что добавленная запись: таблица показывает её первой строкой, а не где-то по номеру
  const lastCreatedId = ref(null)
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
      // уровень приоритета по умолчанию — из справочника «Приоритеты» для типа работ
      priority_id: references.value.work_types[0]?.priority_id ?? references.value.priorities.at(-1)?.id ?? '',
      skill_id: references.value.work_types[0]?.skill_id ?? '',
      transport_id: '',
      work_type_id: references.value.work_types[0]?.id ?? '',
      equipment: {}, // { номер оборудования: сколько штук }
      status_id: null, // появится «Новой»
    }
  }

  // выбрали тип работ — подставляем норматив работы на месте, нужный навык и уровень
  // приоритета по умолчанию: навык определяется типом работ, приоритет можно сменить
  function applyWorkTypeNorms(workTypeId) {
    const workType = references.value.work_types.find((item) => item.id === Number(workTypeId))
    if (!workType) return
    form.value.duration_minutes = workType.work_minutes
    form.value.skill_id = workType.skill_id
    form.value.priority_id = workType.priority_id
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
      equipment: Object.fromEntries((request.equipment ?? []).map((item) => [item.equipment_id, item.quantity])),
      status_id: request.status_id,
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
      equipment: equipmentPayload(values.equipment),
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
        lastCreatedId.value = created.id
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

  // перевести заявки в статус. Бэкенд меняет все или ни одной и объясняет, почему нельзя:
  // перехода нет в таблице или в маршруте бригады раньше стоит незакрытая заявка.
  // Заменяем объекты заявок целиком, чтобы отфильтрованный список и карта пересчитались.
  async function setStatus(requestIds, statusId) {
    clearMessages()
    try {
      await setRequestsStatus(requestIds, statusId)
      const changedIds = new Set(requestIds)
      const status = references.value.request_statuses?.find((item) => item.id === statusId)
      // «Новая» ждёт нового расчёта — от прежнего плана бэкенд её отвязал
      const detached = status?.code === 'new'
      requests.value = requests.value.map((request) =>
        changedIds.has(request.id)
          ? {
              ...request,
              status_id: statusId,
              is_active: status?.plannable ?? request.is_active,
              approved_plan_id: detached ? null : request.approved_plan_id,
            }
          : request,
      )
      await refreshDaysWithRequests()
      const name = referenceName(references.value, 'request_statuses', statusId)
      if (requestIds.length === 1) showNotice(`Заявка №${requestIds[0]}: «${name}»`)
      else showNotice(`Переведено в «${name}» заявок: ${requestIds.length}`)
    } catch (error) {
      showError(error)
    }
  }

  // копия отменённой заявки: создаём, перезагружаем список и сразу открываем копию на правку.
  // planDate — копия переезжает на другой день
  async function duplicate(request, planDate = null) {
    clearMessages()
    try {
      const copy = await duplicateRequest(request.id, planDate)
      await Promise.all([load(), refreshDaysWithRequests()])
      const loaded = requests.value.find((item) => item.id === copy.id)
      if (loaded) startEdit(loaded)
      const moved = planDate ? ` с переносом на ${formatDay(planDate)}` : ''
      showNotice(
        `Создана заявка №${copy.id} — копия отменённой №${request.id}${moved}. Поправьте её и сохраните`,
      )
      return copy.id
    } catch (error) {
      showError(error)
      return null
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
  // cancelled: 'skip' — отменённые из файла не переносим, 'as_new' — переносим «Новыми»
  async function importDay(file, cancelled = 'skip') {
    saving.value = true
    clearMessages()
    try {
      const report = await importRequestsCsv(file, selectedDay.value, cancelled)
      await load()
      showNotice(
        `В день ${formatDay(selectedDay.value)} добавлено заявок: ${report.created}` +
          (report.updated ? `, обновлено ${report.updated}` : '') +
          (report.skipped_cancelled ? `, отменённые не переносились: ${report.skipped_cancelled}` : ''),
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
    lastCreatedId,
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
    duplicate,
    setStatus,
    showNotice,
  }
}
