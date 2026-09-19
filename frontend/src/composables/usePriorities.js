// Справочник «Приоритеты»: уровни приоритета и какой уровень подставляется новой заявке
// каждого типа работ. Уровень по умолчанию меняет администратор; в самой заявке его можно сменить.

import { ref } from 'vue'

import { fetchReferences, updateWorkTypePriority } from '../api/referencesApi.js'
import { useMessages } from './useMessages.js'

export function usePriorities() {
  const references = ref({ skills: [], priorities: [], transports: [], work_types: [] })
  const loading = ref(false)
  const savingId = ref(null)
  const { errorMessage, errorDetails, noticeMessage, showError, showNotice, clearMessages } = useMessages()

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

  // выбрали уровень в строке типа работ — сохраняем сразу
  async function changePriority(workType, priorityId) {
    savingId.value = workType.id
    clearMessages()
    try {
      const saved = await updateWorkTypePriority(workType.id, Number(priorityId))
      references.value = {
        ...references.value,
        work_types: references.value.work_types.map((item) => (item.id === saved.id ? saved : item)),
      }
      const level = references.value.priorities.find((item) => item.id === saved.priority_id)
      showNotice(`«${saved.name}»: новые заявки получат уровень «${level?.name ?? saved.priority_id}»`)
    } catch (error) {
      showError(error)
    } finally {
      savingId.value = null
    }
  }

  return { references, loading, savingId, errorMessage, errorDetails, noticeMessage, load, changePriority }
}
