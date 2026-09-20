// Утверждённый план выбранного дня и есть ли повод его пересчитать. Оператор работает
// в «Заявках» и значка «!» в списке планов не видит, поэтому сигнал показываем прямо там.
// Подробности (какие заявки сняты, какие новые) — уже в самом плане, по ссылке.

import { computed, ref } from 'vue'

import { listPlans } from '../api/plansApi.js'
import { replanHint } from '../utils/replanHint.js'
import { useSelectedDay } from './useSelectedDay.js'

export function useDayPlanWarning() {
  const { selectedDay } = useSelectedDay()
  const summary = ref(null)
  let loadRequest = 0

  // действующий утверждённый план дня: по нему сейчас ездят бригады
  async function load() {
    const request = ++loadRequest
    const day = selectedDay.value
    summary.value = null
    if (!day) return
    try {
      const plans = await listPlans(day)
      if (request !== loadRequest || day !== selectedDay.value) return
      summary.value = plans.find((plan) => plan.approved_at && !plan.superseded_at) ?? null
    } catch {
      if (request !== loadRequest || day !== selectedDay.value) return
      // предупреждение — подсказка, а не работа: молча не показываем его
      summary.value = null
    }
  }

  return {
    planSummary: summary,
    // есть ли повод пересчитать: снятые заявки, новые заявки дня, аварийные, отставание бригад
    needsReplan: computed(() => Boolean(summary.value && replanHint(summary.value))),
    load,
  }
}
