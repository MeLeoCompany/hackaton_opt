// Справочник бригад офиса: бригада работает в регионе своего офиса, её смены на день — это
// исполнители. Логин и пароль — вход бригады в мобильное приложение, как у пользователей:
// пароль задаётся при первом входе, при правке пустое поле значит «оставить прежний».

import { ref } from 'vue'

import { createBrigade, deleteBrigade, listBrigades, updateBrigade } from '../api/brigadesApi.js'
import { useMessages } from './useMessages.js'

export const NEW_BRIGADE = 'new'

export function useBrigades() {
  const brigades = ref([])
  const loading = ref(false)
  const saving = ref(false)
  const { errorMessage, errorDetails, noticeMessage, showError, showNotice, clearMessages } = useMessages()

  const editingId = ref(null)
  const form = ref(null)

  async function load() {
    loading.value = true
    clearMessages()
    try {
      brigades.value = await listBrigades()
    } catch (error) {
      showError(error)
    } finally {
      loading.value = false
    }
  }

  function startCreate() {
    clearMessages()
    editingId.value = NEW_BRIGADE
    form.value = { name: '', login: '', password: '', is_active: true, hasLogin: false }
  }

  function startEdit(brigade) {
    clearMessages()
    editingId.value = brigade.id
    form.value = {
      name: brigade.name,
      login: brigade.login ?? '',
      password: '',
      is_active: brigade.is_active,
      hasLogin: Boolean(brigade.login),
    }
  }

  function cancelEdit() {
    editingId.value = null
    form.value = null
  }

  async function saveForm() {
    const values = form.value
    const payload = {
      name: values.name.trim(),
      login: values.login.trim() || null,
      password: values.password || null,
      is_active: values.is_active,
    }
    saving.value = true
    clearMessages()
    try {
      if (editingId.value === NEW_BRIGADE) await createBrigade(payload)
      else await updateBrigade(editingId.value, payload)
      cancelEdit()
      await load()
      showNotice(`Бригада «${payload.name}» сохранена`)
    } catch (error) {
      showError(error)
    } finally {
      saving.value = false
    }
  }

  async function remove(brigade) {
    if (!window.confirm(`Удалить бригаду «${brigade.name}»? Её вход в приложение тоже удалится.`)) return
    saving.value = true
    clearMessages()
    try {
      await deleteBrigade(brigade.id)
      await load()
      showNotice(`Бригада «${brigade.name}» удалена`)
    } catch (error) {
      showError(error)
    } finally {
      saving.value = false
    }
  }

  return {
    brigades,
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
