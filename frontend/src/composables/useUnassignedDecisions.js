// Решения по заявкам, на которые не успеваем (docs/algoV2.md, шаги 3-4): оператор обзванивает
// клиентов и по каждой заявке отмечает ответ. Общее для пересчёта утверждённого плана и для
// утверждения черновика; allowSkip — при утверждении заявку можно оставить «Новой» без решения.

import { computed, reactive, ref } from 'vue'

import { fromMoscowInputValue, moscowTimeOf, nextDay } from '../utils/moscowTime.js'

const TIME = /^\d\d:\d\d$/

export function useUnassignedDecisions(planDate, { allowSkip = false } = {}) {
  // ответ второго расчёта; null — ещё не проверяли
  const preview = ref(null)
  // решение по каждой заявке: { action: 'agree' | 'move' | 'cancel' | 'no_answer' | 'skip', date, from, to, reason }
  const decisions = reactive({})

  const problems = computed(() => preview.value?.unassigned ?? [])
  const tolerance = computed(() => preview.value?.promise_tolerance_minutes ?? 30)

  function setPreview(result) {
    for (const problem of result?.unassigned ?? []) {
      // есть предложение из второго расчёта — начинаем разговор с него; иначе при пересчёте
      // заявка уезжает на завтра, а при утверждении пока остаётся как есть
      decisions[problem.request_id] = {
        action: problem.suggested_start ? 'agree' : allowSkip ? 'skip' : 'move',
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
  // сколько заявок решено — без «пока не решать»
  const decidedCount = computed(
    () => problems.value.filter((problem) => decisions[problem.request_id]?.action !== 'skip').length,
  )

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
    return problems.value
      .filter((problem) => decisions[problem.request_id]?.action !== 'skip')
      .map(decisionPayload)
  }

  return { preview, decisions, problems, tolerance, setPreview, decisionsReady, decidedCount, payload }
}
