// Справочник оборудования: загрузка, добавление, правка строки и удаление.
// Тип, который требуют заявки, бэкенд удалить не даст (409) — сообщение покажем как есть.

import { ref } from 'vue'

import { createEquipment, deleteEquipment, listEquipment, updateEquipment } from '../api/equipmentApi.js'
import { useMessages } from './useMessages.js'

export const NEW_EQUIPMENT = 'new'

export function useEquipment() {
  const equipment = ref([])
  const loading = ref(false)
  const saving = ref(false)
  const { errorMessage, errorDetails, noticeMessage, showError, showNotice, clearMessages } = useMessages()

  // какая строка редактируется: номер типа, NEW_EQUIPMENT для нового или null
  const editingId = ref(null)
  const form = ref(null)

  async function load() {
    loading.value = true
    clearMessages()
    try {
      equipment.value = await listEquipment()
    } catch (error) {
      showError(error)
    } finally {
      loading.value = false
    }
  }

  function startCreate() {
    clearMessages()
    editingId.value = NEW_EQUIPMENT
    form.value = { name: '', description: '' }
  }

  function startEdit(item) {
    clearMessages()
    editingId.value = item.id
    form.value = { name: item.name, description: item.description }
  }

  function cancelEdit() {
    editingId.value = null
    form.value = null
  }

  async function saveForm() {
    const payload = { name: form.value.name.trim(), description: form.value.description.trim() }
    saving.value = true
    clearMessages()
    try {
      if (editingId.value === NEW_EQUIPMENT) await createEquipment(payload)
      else await updateEquipment(editingId.value, payload)
      cancelEdit()
      await load()
      showNotice(`«${payload.name}» сохранено`)
    } catch (error) {
      showError(error)
    } finally {
      saving.value = false
    }
  }

  async function remove(item) {
    if (!window.confirm(`Удалить «${item.name}» из справочника оборудования?`)) return
    saving.value = true
    clearMessages()
    try {
      await deleteEquipment(item.id)
      await load()
      showNotice(`«${item.name}» удалено`)
    } catch (error) {
      showError(error)
    } finally {
      saving.value = false
    }
  }

  return {
    equipment,
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
