// Решения по заявкам, на которые не успеваем (docs/algoV2.md, шаги 3-4): оператор обзванивает
// клиентов и по каждой заявке отмечает ответ. Общее для пересчёта утверждённого плана и для
// утверждения черновика: и там, и там решение нужно по каждой заявке.

import { computed, reactive, ref } from 'vue'

import { fromMoscowInputValue, moscowTimeOf, nextDay } from '../utils/moscowTime.js'

const TIME = /^\d\d:\d\d$/

export function useUnassignedDecisions(planDate) {
  // ответ второго расчёта; null — ещё не проверяли
  const preview = ref(null)
  // решение по каждой заявке: { action: 'agree' | 'move' | 'cancel' | 'no_answer', date, from, to, reason }
  const decisions = reactive({})

  const problems = computed(() => preview.value?.unassigned ?? [])
  const tolerance = computed(() => preview.value?.promise_tolerance_minutes ?? 30)

  function setPreview(result) {
    for (const problem of result?.unassigned ?? []) {
      // есть предложение из второго расчёта — начинаем разговор с него, иначе — на завтра
      decisions[problem.request_id] = {
        action: problem.suggested_start ? 'agree' : 'move',
        date: nextDay(planDate()),
        from: moscowTimeOf(problem.window_start),
        to: moscowTimeOf(problem.window_end),
        reason: '',
      }
    }
    preview.value = result
  }

  // окно на другой день из полей: конец не позже начала — окно через полночь, конец на следующие сутки
  function windowOf(decision) {
    const start = `${decision.date}T${decision.from}`
    const endDate = decision.to <= decision.from ? nextDay(decision.date) : decision.date
    return { window_start: fromMoscowInputValue(start), window_end: fromMoscowInputValue(`${endDate}T${decision.to}`) }
  }

  function decisionReady(problem) {
    const decision = decisions[problem.request_id]
    if (!decision) return false
    if (decision.action === 'agree') return Boolean(problem.suggested_start)
    if (decision.action === 'move') return Boolean(decision.date) && TIME.test(decision.from) && TIME.test(decision.to)
    if (decision.action === 'cancel') return decision.reason.trim().length > 0
    return true
  }

  const decisionsReady = computed(() => problems.value.every(decisionReady))

  function decisionPayload(problem) {
    const decision = decisions[problem.request_id]
    if (decision.action === 'agree') {
      // утверждаем ровно то окно, которое оператор назвал клиенту
      return {
        request_id: problem.request_id,
        action: 'agree',
        window_start: problem.suggested_start,
        window_end: problem.suggested_end,
      }
    }
    if (decision.action === 'move') {
      return { request_id: problem.request_id, action: 'move', ...windowOf(decision) }
    }
    return { request_id: problem.request_id, action: decision.action, reason: decision.reason.trim() }
  }

  function payload() {
    return problems.value.map(decisionPayload)
  }

  return { preview, decisions, problems, tolerance, setPreview, decisionsReady, payload }
}
