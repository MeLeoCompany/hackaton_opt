// Переходы между вкладками: из сравнения в план (кликнули по плану — открываем «Планы» на нём)
// и из плана в заявку (из карточки визита — открываем «Заявки» на этой заявке).
// Состояние общее на приложение (ref объявлен в модуле), как и выбранный день.

import { ref } from 'vue'

const STORAGE_KEY = 'routing.activeTab'

const activeTab = ref('')
// номер плана, который нужно открыть на вкладке планов; читается один раз и сбрасывается
const pendingPlanId = ref(null)
// то же для заявки: из маршрута исполнителя — к исходной заявке на вкладке «Заявки»
const pendingRequestId = ref(null)

export function usePlanFocus() {
  function openTab(tab) {
    activeTab.value = tab
    try {
      window.localStorage.setItem(STORAGE_KEY, tab)
    } catch {
      // не смогли запомнить — вкладка просто не переживёт перезагрузку
    }
  }

  // из сравнения: открыть конкретный план
  function openPlan(planId) {
    pendingPlanId.value = planId
    openTab('plans')
  }

  function takePlanId() {
    const planId = pendingPlanId.value
    pendingPlanId.value = null
    return planId
  }

  // из маршрута плана: показать заявку такой, какой её завели
  function openRequest(requestId) {
    pendingRequestId.value = requestId
    openTab('requests')
  }

  function takeRequestId() {
    const requestId = pendingRequestId.value
    pendingRequestId.value = null
    return requestId
  }

  return { activeTab, openTab, openPlan, takePlanId, openRequest, takeRequestId }
}
