// Сообщения вкладки: ошибка (остаётся на странице, пока не начнётся следующее действие)
// и уведомление об успехе (всплывает и само исчезает).

import { ref } from 'vue'

const NOTICE_VISIBLE_MS = 5000

export function useMessages() {
  const errorMessage = ref('')
  const errorDetails = ref([]) // список причин, например ошибки по строкам CSV
  const noticeMessage = ref('')
  let noticeTimer = null

  function showError(error) {
    errorMessage.value = error.message
    errorDetails.value = error.details ?? []
  }

  function showNotice(text) {
    noticeMessage.value = text
    clearTimeout(noticeTimer)
    noticeTimer = setTimeout(() => {
      noticeMessage.value = ''
    }, NOTICE_VISIBLE_MS)
  }

  function clearMessages() {
    errorMessage.value = ''
    errorDetails.value = []
    noticeMessage.value = ''
    clearTimeout(noticeTimer)
  }

  return { errorMessage, errorDetails, noticeMessage, showError, showNotice, clearMessages }
}
