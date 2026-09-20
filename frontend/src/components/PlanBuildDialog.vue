<script setup>
// Параметры расчёта плана: окно открывается по кнопке «Построить план», поля заполнены
// значениями по умолчанию — можно сразу нажать «Рассчитать».
// С replanOf — пересчёт утверждённого плана с текущего момента: выполненные и начатые заявки
// остаются за бригадами, бригады стартуют оттуда, где они сейчас, остальное раскладывается заново.
import { computed, reactive, ref, watch } from 'vue'

import { previewReplan } from '../api/plansApi.js'
import { formatDay, fromMoscowInputValue, moscowTimeOf, nextDay } from '../utils/moscowTime.js'
import { objectiveOrder } from '../utils/planningPriorities.js'
import InfoHint from './InfoHint.vue'
import TimeInput from './TimeInput.vue'

const props = defineProps({
  planDate: { type: String, required: true },
  building: { type: Boolean, required: true },
  // ответ /plans/day-check: заявки дня, уже закреплённые за утверждёнными планами других дней
  dayCheck: { type: Object, default: null },
  // сводка утверждённого плана, который пересчитываем; null — обычный расчёт дня
  replanOf: { type: Object, default: null },
  // маршруты пересчитываемого плана: по ним видно, кто ждёт плана, и куда вписать «освободится в»
  routes: { type: Array, default: () => [] },
})
const emit = defineEmits(['build', 'close'])

const SOLVERS = [
  {
    value: 'cuopt',
    label: 'cuOpt — глобальная оптимизация',
    hint: 'Считает на видеокарте NVIDIA: максимум аварийных заявок, затем высокого приоритета, затем всех заявок, меньше исполнителей и пробега',
  },
  {
    value: 'baseline',
    label: 'Базовый — первый подходящий исполнитель',
    hint: 'Контрольный алгоритм ТЗ: заявки по порядку поступления, без перестановок. Считается мгновенно',
  },
]

// значения по умолчанию: ими же расчёт и запускается, если ничего не менять
const params = reactive({
  solver: 'cuopt',
  // что важнее сразу после уровней приоритета: заявки, бригады или пробег
  nextGoal: 'assigned_requests',
})

// заявки с окном через полночь мог забрать утверждённый план соседнего дня — предупреждаем до расчёта
const heldRequests = computed(() => props.dayCheck?.held_requests ?? [])
const heldHolders = computed(() =>
  [...new Set(heldRequests.value.map((held) => `№${held.plan_id} от ${formatDay(held.plan_date)}`))].join(', ')
)
const heldNumbers = computed(() => heldRequests.value.map((held) => `№${held.request_id}`).join(', '))

function solverHint() {
  return SOLVERS.find((solver) => solver.value === params.solver)?.hint ?? ''
}

function basePayload() {
  const payload = { solver: params.solver }
  // момент пересчёта бэкенд берёт сам — текущее системное время
  if (props.replanOf) payload.free_at = freeAtPayload()
  if (params.solver === 'cuopt') payload.objective_order = objectiveOrder(params.nextGoal)
  return payload
}

// ---- пересчёт: сначала пробный, чтобы до пересчёта обзвонить клиентов заявок,
// на которые не успеваем: второй расчёт подбирает время, оператор решает по каждой
// (docs/algoV2.md, шаги 3-4) ----

const preview = ref(null) // ответ пробного пересчёта; null — ещё не проверяли
const previewing = ref(false)
const previewError = ref('')
// решение по каждой невлезшей заявке: { action: 'agree' | 'move' | 'cancel' | 'no_answer', date, from, to, reason }
const decisions = reactive({})
// со слов бригады: когда она освободится, если застряла на заявке (шаг 10)
const freeAt = reactive({})

// поменяли решатель или время «освободится в» — прошлая проверка уже не про этот расчёт
watch([params, freeAt], () => {
  preview.value = null
  previewError.value = ''
})

const problems = computed(() => preview.value?.unassigned ?? [])
const tolerance = computed(() => preview.value?.promise_tolerance_minutes ?? 30)

// бригады, которые выбились из плана: им звонят и уточняют, когда освободятся
const waitingRoutes = computed(() =>
  props.routes.filter((route) => route.waiting_reason || route.delay_minutes > 0),
)

async function checkReplan() {
  previewing.value = true
  previewError.value = ''
  try {
    const result = await previewReplan(props.replanOf.id, basePayload())
    for (const problem of result.unassigned) {
      // есть предложение из второго расчёта — начинаем разговор с него, иначе остаётся завтра
      decisions[problem.request_id] = {
        action: problem.suggested_start ? 'agree' : 'move',
        date: nextDay(props.planDate),
        from: moscowTimeOf(problem.window_start),
        to: moscowTimeOf(problem.window_end),
        reason: '',
      }
    }
    preview.value = result
    return result
  } catch (error) {
    previewError.value = [error.message, ...(error.details ?? [])].join(': ')
    return null
  } finally {
    previewing.value = false
  }
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
  if (decision.action === 'move') {
    return decision.date && /^\d\d:\d\d$/.test(decision.from) && /^\d\d:\d\d$/.test(decision.to)
  }
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

function freeAtPayload() {
  return Object.entries(freeAt)
    .filter(([, time]) => /^\d\d:\d\d$/.test(time ?? ''))
    .map(([engineerId, time]) => ({
      engineer_id: Number(engineerId),
      free_at: fromMoscowInputValue(`${props.planDate}T${time}`),
    }))
}

async function submit() {
  if (!props.replanOf) {
    emit('build', basePayload())
    return
  }
  // первый шаг — пробный пересчёт; не на что решать — сразу пересчитываем
  if (preview.value === null) {
    const result = await checkReplan()
    if (!result || result.unassigned.length) return
  }
  const payload = basePayload()
  payload.decisions = problems.value.map(decisionPayload)
  emit('build', payload)
}
</script>

<template>
  <div class="dialog-backdrop" @click.self="emit('close')">
    <div class="dialog" role="dialog" aria-label="Параметры расчёта плана">
      <header>
        <strong v-if="replanOf">Пересчёт плана №{{ replanOf.id }} · {{ formatDay(planDate) }}</strong>
        <strong v-else>Параметры расчёта · {{ formatDay(planDate) }}</strong>
        <button class="close" title="Закрыть" @click="emit('close')">×</button>
      </header>

      <p v-if="replanOf" class="hint">
        Считаем с текущего момента. Выполненные и начатые заявки остаются за бригадами. Бригады
        продолжают оттуда, где они сейчас, — по отметкам в мобильном приложении. Не начатые и новые
        заявки дня раскладываются заново; куда уже не успеть, останется неназначенным. Получится
        новый план — утвердите его, и он заменит план №{{ replanOf.id }}.
      </p>

      <label class="field">
        <span>Алгоритм</span>
        <select v-model="params.solver" :disabled="building">
          <option v-for="solver in SOLVERS" :key="solver.value" :value="solver.value">
            {{ solver.label }}
          </option>
        </select>
      </label>
      <p class="hint">{{ solverHint() }}</p>

      <fieldset v-if="params.solver === 'cuopt'" class="priority-settings" :disabled="building">
        <legend>Порядок целей</legend>
        <label class="field">
          <span>
            Дальше важнее
            <InfoHint
              text="Уровни приоритета и отметки идут первыми всегда: авария и обещанное клиенту время сильнее любой экономии. Дальше выбираете вы. «Меньше бригад» и «меньше пробега» выше заявок — значит обычную заявку ради экономии могут и не взять."
            />
          </span>
          <select v-model="params.nextGoal">
            <option value="assigned_requests">Максимум заявок</option>
            <option value="engineers_used">Меньше задействованных бригад</option>
            <option value="travel_distance">Меньше общего пробега</option>
          </select>
        </label>
        <p class="hint">
          Все цели остаются в расчёте, порядок строгий: более важная цель всегда сильнее любых
          улучшений нижних уровней.
        </p>
      </fieldset>

      <p v-if="heldRequests.length && !replanOf" class="warning">
        <span class="mark">!</span>
        <span>
          Заявок этого дня закреплено за утверждёнными планами других дней:
          {{ heldRequests.length }} ({{ heldNumbers }}). Забрали: {{ heldHolders }}.
          В расчёт они не пойдут — иначе одну заявку выполнят дважды.
          Нужны здесь — пересчитайте тот план и в его диалоге перенесите заявку на этот день;
          пока по нему ещё не работают, можно снять утверждение.
        </span>
      </p>

      <p v-if="previewError" class="problem-error">{{ previewError }}</p>

      <!-- пересчёт: бригады, выбившиеся из плана, — оператор уточняет по телефону время -->
      <section v-if="replanOf && waitingRoutes.length" class="waiting">
        <h4>Выбились из плана: {{ waitingRoutes.length }}</h4>
        <p class="hint">
          Застрявшая бригада не уложится в норматив: укажите время со слов бригады, и пересчёт
          посчитает её свободной с него, а не с планового конца работы.
        </p>
        <article v-for="route in waitingRoutes" :key="route.engineer_id" class="waiting-row">
          <strong>{{ route.engineer_name }}</strong>
          <a v-if="route.phone" class="phone" :href="`tel:${route.phone}`">{{ route.phone }}</a>
          <span class="muted">{{ route.waiting_reason || `отстаёт на ${route.delay_minutes} мин` }}</span>
          <label class="free-at">
            освободится в
            <TimeInput
              v-model="freeAt[route.engineer_id]"
              :aria-label="`когда освободится бригада ${route.engineer_name}`"
            />
          </label>
        </article>
      </section>

      <!-- пересчёт: заявки, на которые не успеваем, — решение по каждой до пересчёта -->
      <section v-if="problems.length" class="problems">
        <h4>Не успеваем: {{ problems.length }} — обзвоните клиентов</h4>
        <p class="hint">
          Пробный расчёт разложил {{ preview.assigned_count }} заявок. По остальным второй расчёт
          с раскрытыми окнами подобрал время, которое можно предложить клиенту. Решение нужно по
          каждой: либо согласованное окно, либо завтра, либо отмена. Применятся вместе с пересчётом.
        </p>
        <article v-for="problem in problems" :key="problem.request_id" class="problem">
          <div class="problem-head">
            <strong>№{{ problem.request_id }}</strong>
            <span>{{ problem.address }}</span>
            <span class="muted">окно {{ moscowTimeOf(problem.window_start) }}–{{ moscowTimeOf(problem.window_end) }}</span>
            <span v-if="problem.expired" class="chip">окно закрылось</span>
          </div>
          <p class="problem-reason">{{ problem.reason }}</p>
          <p v-if="problem.suggested_start" class="problem-offer">
            {{ problem.suggested_engineer }} приедет в {{ moscowTimeOf(problem.suggested_start) }} —
            предложите клиенту {{ moscowTimeOf(problem.suggested_start) }}–{{ moscowTimeOf(problem.suggested_end) }}
            (допуск {{ tolerance }} мин)
          </p>
          <p v-else class="problem-offer muted">Сегодня не успеть ни при каком окне</p>
          <div class="problem-actions">
            <select
              v-model="decisions[problem.request_id].action"
              :aria-label="`что ответил клиент по заявке №${problem.request_id}`"
            >
              <option value="agree" :disabled="!problem.suggested_start">Согласен на предложенное окно</option>
              <option value="move">Сегодня не может — перенести</option>
              <option value="cancel">Работа не нужна</option>
              <option value="no_answer">Не дозвонились</option>
            </select>
            <template v-if="decisions[problem.request_id].action === 'move'">
              <input v-model="decisions[problem.request_id].date" type="date" aria-label="день нового окна" />
              <TimeInput v-model="decisions[problem.request_id].from" aria-label="начало нового окна" />
              <span>–</span>
              <TimeInput v-model="decisions[problem.request_id].to" aria-label="конец нового окна" />
            </template>
            <input
              v-if="decisions[problem.request_id].action === 'cancel'"
              v-model="decisions[problem.request_id].reason"
              class="reason"
              placeholder="причина отмены"
              :aria-label="`причина отмены заявки №${problem.request_id}`"
            />
            <span v-if="decisions[problem.request_id].action === 'no_answer'" class="muted">
              отменим с отметкой «требует уточнения»
            </span>
          </div>
        </article>
      </section>

      <footer>
        <span class="hint">Заявки и смены берутся на {{ formatDay(planDate) }}</span>
        <div class="dialog-actions">
          <button
            class="primary"
            :disabled="building || previewing || !decisionsReady"
            @click="submit"
          >
            {{
              building || previewing
                ? 'Считаю…'
                : !replanOf
                  ? 'Рассчитать'
                  : problems.length
                    ? 'Применить и пересчитать'
                    : 'Пересчитать'
            }}
          </button>
          <button :disabled="building" @click="emit('close')">Отмена</button>
        </div>
      </footer>
    </div>
  </div>
</template>

<style scoped>
.dialog-backdrop {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgb(15 23 42 / 45%);
}

.dialog {
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: min(520px, 92vw);
  padding: 14px;
  border-radius: 10px;
  background: #fff;
  box-shadow: 0 12px 32px rgb(15 23 42 / 30%);
}

.dialog header,
.dialog footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.close {
  padding: 0 8px;
  font-size: 18px;
  line-height: 26px;
}

.hint {
  margin: 0;
  color: #64748b;
  font-size: 12px;
}

/* пересчёт с заявками, на которые не успеваем: окно шире, список решений */
.dialog:has(.problems),
.dialog:has(.waiting) {
  width: min(760px, 94vw);
  max-height: 90vh;
  overflow: auto;
}

.problems {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 12px;
  border: 1px solid #fecaca;
  border-radius: 8px;
  background: #fef2f2;
}

.problems h4 {
  margin: 0;
  color: #991b1b;
  font-size: 14px;
}

.problem {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px 10px;
  border-radius: 8px;
  background: #fff;
  font-size: 13px;
}

.problem-head {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: baseline;
}

.problem-reason {
  margin: 0;
  color: #b91c1c;
  font-size: 12px;
}

.problem-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}

.problem-actions select {
  width: auto;
}

.problem-actions input[type='date'] {
  width: 150px;
}

.problem-offer {
  margin: 0;
  color: #166534;
  font-size: 12px;
}

.problem-offer.muted,
.problem-actions .muted,
.waiting-row .muted {
  color: #64748b;
}

.chip {
  padding: 1px 6px;
  border-radius: 999px;
  background: #fee2e2;
  color: #991b1b;
  font-size: 11px;
}

.problem-actions .reason {
  width: 220px;
}

.waiting {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 12px;
  border: 1px solid #fcd34d;
  border-radius: 8px;
  background: #fffbeb;
}

.waiting h4 {
  margin: 0;
  color: #92400e;
  font-size: 14px;
}

.waiting-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border-radius: 8px;
  background: #fff;
  font-size: 13px;
}

.waiting-row .free-at {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-left: auto;
  color: #334155;
  font-size: 12px;
}

.problem-error {
  margin: 0;
  color: #b91c1c;
  font-size: 13px;
}

.warning {
  display: flex;
  gap: 8px;
  margin: 0;
  padding: 8px 10px;
  border: 1px solid #fcd34d;
  border-radius: 8px;
  background: #fffbeb;
  color: #92400e;
  font-size: 12px;
  line-height: 1.4;
}

.warning .mark {
  display: inline-flex;
  flex: none;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #f59e0b;
  color: #fff;
  font-weight: 700;
}

.dialog-actions {
  display: flex;
  gap: 8px;
}

.priority-settings {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 0;
  padding: 10px;
  border: 1px solid #dbeafe;
  border-radius: 8px;
  background: #f8fbff;
}

.priority-settings legend {
  padding: 0 5px;
  color: #334155;
  font-size: 12px;
  font-weight: 600;
}
</style>
