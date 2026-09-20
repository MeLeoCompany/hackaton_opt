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

  // действующий утверждённый план дня: по нему сейчас ездят бригады
  async function load() {
    if (!selectedDay.value) return
    try {
      const plans = await listPlans(selectedDay.value)
      summary.value = plans.find((plan) => plan.approved_at && !plan.superseded_at) ?? null
    } catch {
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
