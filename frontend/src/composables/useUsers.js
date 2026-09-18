// Учётки: заводит и правит администратор. Пароль задаётся при создании; при правке пустое
// поле пароля значит «оставить прежний».

import { ref } from 'vue'

import { listOffices } from '../api/officesApi.js'
import { createUser, deleteUser, listUsers, updateUser } from '../api/usersApi.js'
import { useMessages } from './useMessages.js'

export const NEW_USER = 'new'

export const ROLES = [
  { value: 'dispatcher', label: 'Диспетчер' },
  { value: 'admin', label: 'Администратор' },
]

export function useUsers() {
  const users = ref([])
  const offices = ref([])
  const loading = ref(false)
  const saving = ref(false)
  const { errorMessage, errorDetails, noticeMessage, showError, showNotice, clearMessages } = useMessages()

  const editingId = ref(null)
  const form = ref(null)

  async function load() {
    loading.value = true
    clearMessages()
    try {
      const [loadedUsers, loadedOffices] = await Promise.all([listUsers(), listOffices()])
      users.value = loadedUsers
      offices.value = loadedOffices
    } catch (error) {
      showError(error)
    } finally {
      loading.value = false
    }
  }

  function startCreate() {
    clearMessages()
    editingId.value = NEW_USER
    form.value = {
      login: '',
      name: '',
      role: 'dispatcher',
      office_id: offices.value[0]?.id ?? '',
      is_active: true,
      password: '',
    }
  }

  function startEdit(user) {
    clearMessages()
    editingId.value = user.id
    form.value = { ...user, office_id: user.office_id ?? '', password: '' }
  }

  function cancelEdit() {
    editingId.value = null
    form.value = null
  }

  async function saveForm() {
    const values = form.value
    const payload = {
      login: values.login.trim(),
      name: values.name.trim(),
      role: values.role,
      // у администратора офиса нет: он выбирает офис сам
      office_id: values.role === 'admin' || values.office_id === '' ? null : Number(values.office_id),
      is_active: values.is_active,
      password: values.password ? values.password : null,
    }
    saving.value = true
    clearMessages()
    try {
      if (editingId.value === NEW_USER) await createUser(payload)
      else await updateUser(editingId.value, payload)
      cancelEdit()
      await load()
      showNotice(`Учётка «${payload.login}» сохранена`)
    } catch (error) {
      showError(error)
    } finally {
      saving.value = false
    }
  }

  async function remove(user) {
    if (!window.confirm(`Удалить учётку «${user.login}»? Войти под ней больше не получится.`)) return
    saving.value = true
    clearMessages()
    try {
      await deleteUser(user.id)
      await load()
      showNotice(`Учётка «${user.login}» удалена`)
    } catch (error) {
      showError(error)
    } finally {
      saving.value = false
    }
  }

  return {
    users,
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
