// Загрузка заявок из CSV: отдельная вкладка, поэтому и состояние своё, без таблицы заявок.

import { ref } from 'vue'

import { downloadCsvTemplate, importRequestsCsv } from '../api/requestsApi.js'
import { useMessages } from './useMessages.js'

export function useRequestsImport() {
  const saving = ref(false)
  const lastReport = ref(null) // { created, updated } последней удачной загрузки
  const { errorMessage, errorDetails, noticeMessage, showError, showNotice, clearMessages } = useMessages()

  async function importCsv(file) {
    saving.value = true
    lastReport.value = null
    clearMessages()
    try {
      const report = await importRequestsCsv(file)
      lastReport.value = report
      showNotice(`Файл «${file.name}» загружен: добавлено ${report.created}, обновлено ${report.updated}`)
    } catch (error) {
      showError(error)
    } finally {
      saving.value = false
    }
  }

  async function downloadTemplate() {
    clearMessages()
    try {
      const blob = await downloadCsvTemplate()
      const link = document.createElement('a')
      link.href = URL.createObjectURL(blob)
      link.download = 'requests_template.csv'
      link.click()
      setTimeout(() => URL.revokeObjectURL(link.href), 1000)
    } catch (error) {
      showError(error)
    }
  }

  return { saving, lastReport, errorMessage, errorDetails, noticeMessage, importCsv, downloadTemplate }
}
