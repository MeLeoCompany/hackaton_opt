// Переход из сравнения в план: кликнули по плану — открываем вкладку «Планы» на нём.
// Подробности по заявкам живут в самом плане, здесь их не дублируем.
// Состояние общее на приложение (ref объявлен в модуле), как и выбранный день.

import { ref } from 'vue'

const STORAGE_KEY = 'routing.activeTab'

const activeTab = ref('')
// номер плана, который нужно открыть на вкладке планов; читается один раз и сбрасывается
const pendingPlanId = ref(null)

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

  return { activeTab, openTab, openPlan, takePlanId }
}
