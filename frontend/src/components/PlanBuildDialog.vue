<script setup>
// Параметры расчёта плана: окно открывается по кнопке «Построить план», поля заполнены
// значениями по умолчанию — можно сразу нажать «Рассчитать».
// С replanOf — пересчёт утверждённого плана с момента: выполненные и начатые заявки остаются
// за бригадами, бригады стартуют оттуда, где они сейчас, остальное раскладывается заново.
import { computed, reactive, ref, watch } from 'vue'

import { previewReplan } from '../api/plansApi.js'
import { formatDay, fromMoscowInputValue, moscowDateOf, moscowTimeOf, nextDay } from '../utils/moscowTime.js'
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

// пояснение к выбору «Сначала выполнить» — во всплывающей подсказке у значка «i»
const SERVICE_HINTS = {
  urgent_requests:
    'Сначала как можно больше аварийных заявок, затем — высокого приоритета, потом все остальные. ' +
    'Уровень заявки — из справочника «Приоритеты».',
  assigned_requests: 'Как можно больше заявок всего, без учёта уровня приоритета.',
}

// значения по умолчанию: ими же расчёт и запускается, если ничего не менять
const params = reactive({
  solver: 'cuopt',
  servicePriority: 'urgent_requests',
  resourcePriority: 'engineers_used',
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

// момент пересчёта: у плана на сегодня — сейчас, у другого дня время выбирают на этот день
const nowIso = new Date().toISOString()
const isToday = moscowDateOf(nowIso) === props.planDate
const replanTime = ref(isToday ? moscowTimeOf(nowIso) : '')
const canSubmit = computed(() => !props.replanOf || /^\d\d:\d\d$/.test(replanTime.value))

function basePayload() {
  const payload = { solver: params.solver }
  if (props.replanOf) payload.at = fromMoscowInputValue(`${props.planDate}T${replanTime.value}`)
  if (params.solver === 'cuopt') {
    payload.objective_order = objectiveOrder(params.servicePriority, params.resourcePriority)
  }
  return payload
}

// ---- пересчёт: сначала пробный, чтобы до пересчёта решить, что делать с заявками,
// на которые не успеваем: новое окно, отменить или оставить неназначенной ----

const preview = ref(null) // ответ пробного пересчёта; null — ещё не проверяли
const previewing = ref(false)
const previewError = ref('')
// решение по каждой проблемной заявке: { action: 'reschedule' | 'cancel' | 'keep', date, from, to }
const decisions = reactive({})

// поменяли момент или решатель — прошлая проверка уже не про этот расчёт
watch([replanTime, params], () => {
  preview.value = null
  previewError.value = ''
})

const problems = computed(() => preview.value?.unassigned ?? [])

async function checkReplan() {
  previewing.value = true
  previewError.value = ''
  try {
    const result = await previewReplan(props.replanOf.id, basePayload())
    for (const problem of result.unassigned) {
      // по умолчанию — то же время завтра: клиенту обычно удобен тот же интервал
      decisions[problem.request_id] = {
        action: 'reschedule',
        date: nextDay(props.planDate),
        from: moscowTimeOf(problem.window_start),
        to: moscowTimeOf(problem.window_end),
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

// новое окно из полей: конец не позже начала — окно через полночь, конец на следующие сутки
function windowOf(decision) {
  const start = `${decision.date}T${decision.from}`
  const endDate = decision.to <= decision.from ? nextDay(decision.date) : decision.date
  return { window_start: fromMoscowInputValue(start), window_end: fromMoscowInputValue(`${endDate}T${decision.to}`) }
}

const decisionsReady = computed(() =>
  problems.value.every((problem) => {
    const decision = decisions[problem.request_id]
    if (decision?.action !== 'reschedule') return true
    return decision.date && /^\d\d:\d\d$/.test(decision.from) && /^\d\d:\d\d$/.test(decision.to)
  }),
)

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
  payload.decisions = problems.value
    .map((problem) => ({ problem, decision: decisions[problem.request_id] }))
    .filter(({ decision }) => decision.action !== 'keep')
    .map(({ problem, decision }) =>
      decision.action === 'cancel'
        ? { request_id: problem.request_id, action: 'cancel' }
        : { request_id: problem.request_id, action: 'reschedule', ...windowOf(decision) },
    )
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

      <template v-if="replanOf">
        <label class="field">
          <span>С какого момента</span>
          <TimeInput v-model="replanTime" aria-label="момент пересчёта" />
        </label>
        <p class="hint">
          Выполненные и начатые заявки остаются за бригадами. Бригады продолжают оттуда, где они
          сейчас, — по отметкам в мобильном приложении. Не начатые и новые заявки дня
          раскладываются заново; куда уже не успеть, останется неназначенным. Получится новый
          план — утвердите его, и он заменит план №{{ replanOf.id }}.
        </p>
      </template>

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
          <span>Сначала выполнить <InfoHint :text="SERVICE_HINTS[params.servicePriority]" /></span>
          <select v-model="params.servicePriority">
            <option value="urgent_requests">По уровням приоритета</option>
            <option value="assigned_requests">Максимум всех заявок</option>
          </select>
        </label>
        <label class="field">
          <span>После этого сократить</span>
          <select v-model="params.resourcePriority">
            <option value="engineers_used">Количество задействованных бригад</option>
            <option value="travel_distance">Общий пробег</option>
          </select>
        </label>
        <p class="hint">
          Все четыре цели остаются в расчёте. Выбор определяет строгий порядок: более важная
          цель всегда сильнее любых улучшений нижних уровней.
        </p>
      </fieldset>

      <p v-if="heldRequests.length && !replanOf" class="warning">
        <span class="mark">!</span>
        <span>
          Заявок этого дня закреплено за утверждёнными планами других дней:
          {{ heldRequests.length }} ({{ heldNumbers }}). Забрали: {{ heldHolders }}.
          В расчёт они не пойдут — иначе одну заявку выполнят дважды.
          Нужны здесь — снимите утверждение с того плана.
        </span>
      </p>

      <p v-if="previewError" class="problem-error">{{ previewError }}</p>

      <!-- пересчёт: заявки, на которые не успеваем, — решение по каждой до пересчёта -->
      <section v-if="problems.length" class="problems">
        <h4>Не успеваем: {{ problems.length }} — решите до пересчёта</h4>
        <p class="hint">
          Пробный расчёт разложил {{ preview.assigned_count }} заявок, а эти не помещаются. Новое окно
          снимет заявку с плана: сегодня — пересчёт попробует её взять, другой день — она уйдёт в его
          план. Решения применятся вместе с пересчётом.
        </p>
        <article v-for="problem in problems" :key="problem.request_id" class="problem">
          <div class="problem-head">
            <strong>№{{ problem.request_id }}</strong>
            <span>{{ problem.address }}</span>
            <span class="muted">окно {{ moscowTimeOf(problem.window_start) }}–{{ moscowTimeOf(problem.window_end) }}</span>
          </div>
          <p class="problem-reason">{{ problem.reason }}</p>
          <div class="problem-actions">
            <select v-model="decisions[problem.request_id].action" :aria-label="`что сделать с заявкой №${problem.request_id}`">
              <option value="reschedule">Новое окно</option>
              <option value="cancel">Отменить заявку</option>
              <option value="keep">Оставить неназначенной</option>
            </select>
            <template v-if="decisions[problem.request_id].action === 'reschedule'">
              <input v-model="decisions[problem.request_id].date" type="date" aria-label="день нового окна" />
              <TimeInput v-model="decisions[problem.request_id].from" aria-label="начало нового окна" />
              <span>–</span>
              <TimeInput v-model="decisions[problem.request_id].to" aria-label="конец нового окна" />
            </template>
          </div>
        </article>
      </section>

      <footer>
        <span class="hint">Заявки и смены берутся на {{ formatDay(planDate) }}</span>
        <div class="dialog-actions">
          <button
            class="primary"
            :disabled="building || previewing || !canSubmit || !decisionsReady"
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
.dialog:has(.problems) {
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
