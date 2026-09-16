// Исполнители: загрузка, добавление, изменение, удаление.
// Фильтры, сортировка и выбор — в useEngineersView.

import { ref, watch } from 'vue'

import { createEngineer, deleteEngineer, listEngineers, updateEngineer } from '../api/engineersApi.js'
import { fetchReferences } from '../api/referencesApi.js'
import { fromMoscowInputValue, toMoscowInputValue } from '../utils/moscowTime.js'
import { useMessages } from './useMessages.js'
import { useSelectedDay } from './useSelectedDay.js'

export const NEW_ENGINEER = 'new'

export function useEngineersTable() {
  const { selectedDay } = useSelectedDay()
  const engineers = ref([])
  const references = ref({ skills: [], priorities: [], transports: [], work_types: [] })

  const loading = ref(false)
  const saving = ref(false)
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
      const [loadedReferences, loadedEngineers] = await Promise.all([
        fetchReferences(),
        listEngineers(day),
      ])
      if (request !== loadRequest) return
      references.value = loadedReferences
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
    form.value = {
      id: '',
      name: '',
      transport_id: references.value.transports[0]?.id ?? '',
      skill_ids: [],
      shift_start: '',
      shift_end: '',
      start_latitude: '',
      start_longitude: '',
    }
  }

  function startEdit(engineer) {
    clearMessages()
    editingId.value = engineer.id
    form.value = {
      id: engineer.id,
      name: engineer.name,
      transport_id: engineer.transport_id,
      skill_ids: [...engineer.skill_ids],
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
      name: values.name.trim(),
      transport_id: numberOrNull(values.transport_id),
      skill_ids: values.skill_ids.map(Number),
      shift_start: values.shift_start ? fromMoscowInputValue(values.shift_start) : null,
      shift_end: values.shift_end ? fromMoscowInputValue(values.shift_end) : null,
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

  // сменили день — список перезагружается на новый день
  watch(selectedDay, () => {
    cancelEdit()
    load()
  })

  return {
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
  }
}
