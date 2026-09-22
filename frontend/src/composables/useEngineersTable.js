// Исполнители: загрузка, добавление, изменение, удаление.
// Фильтры, сортировка и выбор — в useEngineersView.

import { ref, watch } from 'vue'

import {
  createEngineer,
  deleteEngineer,
  exportEngineersCsv,
  importEngineersCsv,
  listEngineers,
  updateEngineer,
} from '../api/engineersApi.js'
import { listBrigades } from '../api/brigadesApi.js'
import { fetchReferences } from '../api/referencesApi.js'
import { downloadBlob } from '../utils/downloadFile.js'
import { fromMoscowInputValue, toMoscowInputValue } from '../utils/moscowTime.js'
import { isAtOffice } from '../utils/officePoint.js'
import { useMessages } from './useMessages.js'
import { useSelectedDay } from './useSelectedDay.js'
import { equipmentPayload } from '../utils/equipment.js'

export const NEW_ENGINEER = 'new'

export function useEngineersTable() {
  const { selectedDay } = useSelectedDay()
  const engineers = ref([])
  const references = ref({ skills: [], priorities: [], transports: [], work_types: [], offices: [] })

  const loading = ref(false)
  const saving = ref(false)
  // только что добавленная запись: таблица показывает её первой строкой, а не где-то по номеру
  const lastCreatedId = ref(null)
  const { errorMessage, errorDetails, noticeMessage, showError, showNotice, clearMessages } = useMessages()

  // какая строка сейчас редактируется: номер исполнителя, NEW_ENGINEER для нового или null
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
      const [loadedReferences, loadedEngineers, loadedBrigades] = await Promise.all([
        fetchReferences(),
        listEngineers(day),
        listBrigades(),
      ])
      if (request !== loadRequest) return
      // бригады офиса — из них выбирают, чья это смена
      references.value = { ...loadedReferences, brigades: loadedBrigades }
      engineers.value = loadedEngineers
    } catch (error) {
      if (request === loadRequest) showError(error)
    } finally {
      if (request === loadRequest) loading.value = false
    }
  }

  function startCreate() {
    clearMessages()
    editingId.value = NEW_ENGINEER
    // как правило бригады выезжают из офиса — новая сразу стоит в своём офисе
    const office = references.value.offices?.[0] ?? null
    form.value = {
      id: '',
      brigade_id: '',
      transport_id: references.value.transports[0]?.id ?? '',
      skill_ids: [],
      equipment: {}, // { номер оборудования: сколько штук }
      shift_start: '',
      shift_end: '',
      start_latitude: office?.latitude ?? '',
      start_longitude: office?.longitude ?? '',
    }
  }

  function startEdit(engineer) {
    clearMessages()
    editingId.value = engineer.id
    form.value = {
      id: engineer.id,
      brigade_id: engineer.brigade_id,
      transport_id: engineer.transport_id,
      skill_ids: [...engineer.skill_ids],
      equipment: Object.fromEntries((engineer.equipment ?? []).map((item) => [item.equipment_id, item.quantity])),
      shift_start: toMoscowInputValue(engineer.shift_start),
      shift_end: toMoscowInputValue(engineer.shift_end),
      start_latitude: engineer.start_latitude,
      start_longitude: engineer.start_longitude,
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
      brigade_id: numberOrNull(values.brigade_id),
      transport_id: numberOrNull(values.transport_id),
      skill_ids: values.skill_ids.map(Number),
      equipment: equipmentPayload(values.equipment),
      shift_start: values.shift_start ? fromMoscowInputValue(values.shift_start) : null,
      shift_end: values.shift_end ? fromMoscowInputValue(values.shift_end) : null,
      // координаты совпали с офисом — бригада выезжает из офиса и переедет вместе с ним
      start_at_office: isAtOffice(values.start_latitude, values.start_longitude, references.value.offices?.[0]),
      start_latitude: numberOrNull(values.start_latitude),
      start_longitude: numberOrNull(values.start_longitude),
    }
  }

  async function saveForm() {
    saving.value = true
    clearMessages()
    try {
      const payload = formToPayload()
      let notice
      if (editingId.value === NEW_ENGINEER) {
        const created = await createEngineer({ ...payload, id: numberOrNull(form.value.id) })
        notice = `Исполнитель «${created.name}» добавлен`
        lastCreatedId.value = created.id
      } else {
        const updated = await updateEngineer(editingId.value, payload)
        notice = `Исполнитель «${updated.name}» сохранён`
      }
      cancelEdit()
      await load()
      showNotice(notice)
    } catch (error) {
      showError(error)
    } finally {
      saving.value = false
    }
  }

  async function remove(engineer) {
    if (!window.confirm(`Удалить исполнителя «${engineer.name}»?`)) return
    clearMessages()
    try {
      await deleteEngineer(engineer.id)
      engineers.value = engineers.value.filter((item) => item.id !== engineer.id)
      showNotice(`Исполнитель «${engineer.name}» удалён`)
    } catch (error) {
      showError(error)
    }
  }

  // ---- слепок дня ----

  async function exportDay() {
    clearMessages()
    try {
      downloadBlob(await exportEngineersCsv(selectedDay.value), `engineers_${selectedDay.value}.csv`)
    } catch (error) {
      showError(error)
    }
  }

  // Файл кладётся в выбранный день копией: время смен то же, номера новые.
  // Существующих исполнителей дня не трогаем: они могут быть в планах, и их удаление
  // либо сломало бы план, либо упёрлось в запрет удаления. Поэтому только предупреждаем.
  async function importDay(file) {
    if (engineers.value.length) {
      const confirmed = window.confirm(
        `На этот день уже есть исполнителей: ${engineers.value.length}. ` +
          `Из файла «${file.name}» они добавятся копиями, существующие останутся. Продолжить?`,
      )
      if (!confirmed) return
    }
    saving.value = true
    clearMessages()
    try {
      const report = await importEngineersCsv(file, selectedDay.value)
      await load()
      showNotice(
        `В день ${selectedDay.value} добавлено исполнителей: ${report.created}` +
          (report.updated ? `, обновлено ${report.updated}` : ''),
      )
    } catch (error) {
      showError(error)
    } finally {
      saving.value = false
    }
  }

  // сменили день — список перезагружается на новый день
  watch(selectedDay, () => {
    cancelEdit()
    load()
  })

  return {
    lastCreatedId,
    engineers,
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
    exportDay,
    importDay,
  }
}
