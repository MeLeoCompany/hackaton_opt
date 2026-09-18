// Переходы между вкладками: из сравнения в план (кликнули по плану — открываем «Планы» на нём)
// и из плана в заявку (из карточки визита — открываем «Заявки» на этой заявке).
// Состояние общее на приложение (ref объявлен в модуле), как и выбранный день.

import { ref } from 'vue'

const STORAGE_KEY = 'routing.activeTab'

const activeTab = ref('')
// номер плана, который нужно открыть на вкладке планов; читается один раз и сбрасывается
const pendingPlanId = ref(null)
// заявка, которую показать на карте этого плана (пришли из «Заявок»); null — просто план
const pendingPlanRequestId = ref(null)
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

  // из сравнения: открыть конкретный план; из заявки — ещё и показать её на карте плана
  function openPlan(planId, requestId = null) {
    pendingPlanId.value = planId
    pendingPlanRequestId.value = requestId
    openTab('plans')
  }

  function takePlanId() {
    const planId = pendingPlanId.value
    pendingPlanId.value = null
    return planId
  }

  function takePlanRequestId() {
    const requestId = pendingPlanRequestId.value
    pendingPlanRequestId.value = null
    return requestId
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

  return { activeTab, openTab, openPlan, takePlanId, takePlanRequestId, openRequest, takeRequestId }
}
