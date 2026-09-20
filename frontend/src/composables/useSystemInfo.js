// Параметры системы для вкладки «Система»: версии, подключения, настройки, объёмы данных.
// Данные собирает бэкенд (`/system/info`), здесь — загрузка и обновление по кнопке.

import { ref } from 'vue'

import { fetchSystemInfo } from '../api/systemApi.js'
import { useMessages } from './useMessages.js'

export function useSystemInfo() {
  const info = ref(null)
  const loading = ref(false)
  const { errorMessage, errorDetails, showError, clearMessages } = useMessages()

  async function load() {
    loading.value = true
    clearMessages()
    try {
      info.value = await fetchSystemInfo()
    } catch (error) {
      showError(error)
    } finally {
      loading.value = false
    }
  }

  return { info, loading, errorMessage, errorDetails, load }
}
