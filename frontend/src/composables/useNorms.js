// Нормативы типов работ: загрузка и правка строки администратором.
// Норматив — только подстановка по умолчанию: длительность новой заявки при выборе типа
// работ и строки CSV без длительности. У существующих заявок длительность своя.

import { ref } from 'vue'

import { fetchReferences, updateWorkTypeNorms } from '../api/referencesApi.js'
import { useMessages } from './useMessages.js'

export function useNorms() {
  const references = ref({ skills: [], priorities: [], transports: [], work_types: [] })
  const loading = ref(false)
  const saving = ref(false)
  const { errorMessage, errorDetails, noticeMessage, showError, showNotice, clearMessages } = useMessages()

  const editingId = ref(null)
  const form = ref(null)

  async function load() {
    loading.value = true
    clearMessages()
    try {
      references.value = await fetchReferences()
    } catch (error) {
      showError(error)
    } finally {
      loading.value = false
    }
  }

  function startEdit(workType) {
    clearMessages()
    editingId.value = workType.id
    form.value = { travel_minutes: workType.travel_minutes, work_minutes: workType.work_minutes }
  }

  function cancelEdit() {
    editingId.value = null
    form.value = null
  }

  // пустое поле -> null, чтобы бэкенд ответил «не заполнено», а не «не число»
  function numberOrNull(value) {
    return value === '' || value === null || value === undefined ? null : Number(value)
  }

  async function saveForm() {
    const workTypeId = editingId.value
    const payload = {
      travel_minutes: numberOrNull(form.value.travel_minutes),
      work_minutes: numberOrNull(form.value.work_minutes),
    }
    saving.value = true
    clearMessages()
    try {
      const saved = await updateWorkTypeNorms(workTypeId, payload)
      references.value = {
        ...references.value,
        work_types: references.value.work_types.map((item) => (item.id === saved.id ? saved : item)),
      }
      cancelEdit()
      showNotice(`Нормативы «${saved.name}» сохранены: подставятся в новые заявки`)
    } catch (error) {
      showError(error)
    } finally {
      saving.value = false
    }
  }

  return {
    references,
    loading,
    saving,
    errorMessage,
    errorDetails,
    noticeMessage,
    editingId,
    form,
    load,
    startEdit,
    cancelEdit,
    saveForm,
  }
}
