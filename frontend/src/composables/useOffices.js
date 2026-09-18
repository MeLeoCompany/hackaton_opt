// Справочник офисов: загрузка, добавление, правка строки и удаление.

import { ref } from 'vue'

import { createOffice, deleteOffice, listOffices, updateOffice } from '../api/officesApi.js'
import { useMessages } from './useMessages.js'

export const NEW_OFFICE = 'new'

export function useOffices() {
  const offices = ref([])
  const loading = ref(false)
  const saving = ref(false)
  const { errorMessage, errorDetails, noticeMessage, showError, showNotice, clearMessages } = useMessages()

  // какая строка редактируется: номер офиса, NEW_OFFICE для нового или null
  const editingId = ref(null)
  const form = ref(null)

  async function load() {
    loading.value = true
    clearMessages()
    try {
      offices.value = await listOffices()
    } catch (error) {
      showError(error)
    } finally {
      loading.value = false
    }
  }

  function startCreate() {
    clearMessages()
    editingId.value = NEW_OFFICE
    form.value = { name: '', address: '', latitude: '', longitude: '' }
  }

  function startEdit(office) {
    clearMessages()
    editingId.value = office.id
    form.value = {
      name: office.name,
      address: office.address,
      latitude: office.latitude,
      longitude: office.longitude,
    }
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
    const payload = {
      name: form.value.name.trim(),
      address: form.value.address.trim(),
      latitude: numberOrNull(form.value.latitude),
      longitude: numberOrNull(form.value.longitude),
    }
    const before = offices.value.find((office) => office.id === editingId.value)
    saving.value = true
    clearMessages()
    try {
      if (editingId.value === NEW_OFFICE) {
        await createOffice(payload)
        cancelEdit()
        await load()
        showNotice(`Офис «${payload.name}» добавлен`)
        return
      }
      const saved = await updateOffice(editingId.value, payload)
      cancelEdit()
      await load()
      // офис сдвинули — бэкенд перенёс старт его бригад: говорим об этом прямо
      const moved =
        before && saved.engineer_count > 0 &&
        (before.latitude !== saved.latitude || before.longitude !== saved.longitude)
      showNotice(
        moved
          ? `Офис «${saved.name}» сохранён, старт его исполнителей (${saved.engineer_count}) перенесён`
          : `Офис «${saved.name}» сохранён`,
      )
    } catch (error) {
      showError(error)
    } finally {
      saving.value = false
    }
  }

  async function remove(office) {
    const consequence = office.engineer_count
      ? ` Его исполнители (${office.engineer_count}) останутся на тех же координатах как «своя точка».`
      : ''
    if (!window.confirm(`Удалить офис «${office.name}»?${consequence}`)) return
    saving.value = true
    clearMessages()
    try {
      await deleteOffice(office.id)
      await load()
      showNotice(`Офис «${office.name}» удалён`)
    } catch (error) {
      showError(error)
    } finally {
      saving.value = false
    }
  }

  return {
    offices,
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
