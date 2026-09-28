<script setup>
// Параметры расчёта плана: окно открывается по кнопке «Построить план», поля заполнены
// значениями по умолчанию — можно сразу нажать «Рассчитать».
// С replanOf — пересчёт утверждённого плана с текущего момента: выполненные и начатые заявки
// остаются за бригадами, бригады стартуют оттуда, где они сейчас, остальное раскладывается заново.
import { computed, onMounted, reactive, ref, watch } from 'vue'

import { getPlan } from '../api/plansApi.js'
import { fetchSolverParams } from '../api/systemApi.js'
import { limitHint, numericParams } from '../utils/solverParams.js'
import { formatDay, fromMoscowInputValue, moscowTimeOf } from '../utils/moscowTime.js'
import { objectiveOrder } from '../utils/planningPriorities.js'
import InfoHint from './InfoHint.vue'
import SolverParamRows from './SolverParamRows.vue'
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
    value: 'ortools',
    label: 'OR-Tools — та же оптимизация на процессоре',
    hint: 'Та же постановка задачи, что у cuOpt: те же приоритеты, ярусы и цена бригады. Считает на процессоре, видеокарта не нужна',
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

// параметры решателя: по умолчанию системные («Система» → «Параметры расчёта»),
// но на один расчёт их можно поменять прямо здесь
const solverParams = ref(null)
const systemParams = ref(null)
const paramsOpen = ref(false)

onMounted(async () => {
  try {
    const params = await fetchSolverParams()
    solverParams.value = { ...params }
    systemParams.value = { ...params }
  } catch {
    // не ответили — считаем с системными по умолчанию, диалог работает как раньше
  }
})

const paramsChanged = computed(
  () =>
    solverParams.value &&
    JSON.stringify(numericParams(solverParams.value)) !== JSON.stringify(numericParams(systemParams.value)),
)

// заявки с окном через полночь мог забрать утверждённый план соседнего дня — предупреждаем до расчёта
const heldRequests = computed(() => props.dayCheck?.held_requests ?? [])
const heldHolders = computed(() =>
  [...new Set(heldRequests.value.map((held) => `№${held.plan_id} от ${formatDay(held.plan_date)}`))].join(', ')
)
const heldNumbers = computed(() => heldRequests.value.map((held) => `№${held.request_id}`).join(', '))

function solverHint() {
  return SOLVERS.find((solver) => solver.value === params.solver)?.hint ?? ''
}

// как назвать выбранный решатель в заголовке параметров поиска
function solverTitle() {
  return params.solver === 'ortools' ? 'OR-Tools' : 'cuOpt'
}

function basePayload() {
  const payload = { solver: params.solver }
  // момент пересчёта бэкенд берёт сам — текущее системное время
  if (props.replanOf) payload.free_at = freeAtPayload()
  if (params.solver !== 'baseline') {
    payload.objective_order = objectiveOrder(params.nextGoal)
    // системные параметры шлём только когда их поменяли: иначе сервер возьмёт свои
    if (paramsChanged.value) payload.solver_params = numericParams(solverParams.value)
  }
  return payload
}

// ---- пересчёт: первый расчёт круга и только он. По заявкам, которые в него не вошли,
// оператор решает отдельно — кнопками «Подобрать окна» и «Утвердить» у самого пересчёта
// (docs/algoV2.md, шаги 2-5) ----

function close() {
  emit('close')
}

// со слов бригады: когда она освободится, если застряла на заявке (шаг 10)
const freeAt = reactive({})

// где бригада сейчас на месте: отметила «На месте», но ещё не «Выполнено»
function onSiteVisit(route) {
  return route.visits.find((visit) => visit.arrived_at && !visit.finished_at) ?? null
}

// План перечитываем при открытии диалога: из списка маршрутов у страницы нет, а сводка в
// списке могла устареть — пересчёт, который она считает ждущим своего момента, к этой минуте
// мог стать недействительным
const loadedPlan = ref(null)
const planRoutes = computed(() => (props.routes.length ? props.routes : loadedPlan.value?.routes ?? []))
// какой пересчёт этого плана сейчас ждёт своего момента; null — ни одного
const pendingReplanId = computed(
  () => (loadedPlan.value ?? props.replanOf)?.pending_replan_id ?? null,
)

onMounted(async () => {
  if (!props.replanOf) return
  try {
    loadedPlan.value = await getPlan(props.replanOf.id)
  } catch {
    // не прочитали — диалог работает как раньше, время бригады можно вписать при пересчёте
  }
})

// застряли на заявке: бригада на месте и отстаёт — ей звонят и уточняют, когда освободится.
// Закончившая или уже выехавшая свободна по своим отметкам — спрашивать нечего
const waitingRoutes = computed(() =>
  planRoutes.value.filter((route) => onSiteVisit(route) && (route.waiting_reason || route.delay_minutes > 0)),
)

// поле «освободится в» заполняем оценкой с сервера: по нормативу, а если он уже прошёл —
// с запасом от момента пересчёта. Пустое поле означало бы «свободна прямо сейчас», и
// застрявшая бригада снова не выехала бы — день крутился бы в пересчётах (шаг 10)
watch(
  waitingRoutes,
  (routes) => {
    routes.forEach((route) => {
      if (freeAt[route.engineer_id] === undefined && route.free_at_estimate) {
        freeAt[route.engineer_id] = moscowTimeOf(route.free_at_estimate)
      }
    })
  },
  { immediate: true },
)

function stuckText(route) {
  const visit = onSiteVisit(route)
  const late = route.delay_minutes > 0 ? ` · отстаёт на ${route.delay_minutes} мин` : ''
  return `на месте №${visit.request_id} с ${moscowTimeOf(visit.arrived_at)}${late}`
}

function freeAtPayload() {
  return Object.entries(freeAt)
    .filter(([, time]) => /^\d\d:\d\d$/.test(time ?? ''))
    .map(([engineerId, time]) => ({
      engineer_id: Number(engineerId),
      free_at: fromMoscowInputValue(`${props.planDate}T${time}`),
    }))
}

function submit() {
  emit('build', basePayload())
}
</script>

<template>
  <div class="dialog-backdrop" @click.self="close">
    <div class="dialog" role="dialog" aria-label="Параметры расчёта плана">
      <header>
        <strong v-if="replanOf">Пересчёт плана №{{ replanOf.id }} · {{ formatDay(planDate) }}</strong>
        <strong v-else>Параметры расчёта · {{ formatDay(planDate) }}</strong>
        <button class="close" title="Закрыть" @click="close">×</button>
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

      <fieldset v-if="params.solver !== 'baseline'" class="priority-settings" :disabled="building">
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

      <!-- параметры поиска: базовому алгоритму их не передать; подставлены системные,
           можно поменять на этот расчёт -->
      <section v-if="params.solver !== 'baseline' && solverParams" class="solver-block">
        <button type="button" class="link solver-toggle" @click="paramsOpen = !paramsOpen">
          {{ paramsOpen ? '▾' : '▸' }} Параметры {{ solverTitle() }}
          <span class="muted">
            · время поиска {{ solverParams.time_limit_seconds }}–{{ solverParams.max_time_limit_seconds }} c<template
              v-if="paramsChanged"
            >
              · изменены для этого расчёта</template
            >
          </span>
        </button>
        <!-- та же таблица, что в «Системе»: правка здесь действует только на этот расчёт -->
        <template v-if="paramsOpen">
          <table class="data-table params-table">
            <colgroup>
              <col />
              <col style="width: 30%" />
              <col style="width: 84px" />
            </colgroup>
            <thead>
              <tr><th>Параметр</th><th>Значение</th><th></th></tr>
            </thead>
            <tbody>
              <SolverParamRows
                :values="solverParams"
                :baseline="systemParams"
                :disabled="building"
                @update="(key, value) => (solverParams = { ...solverParams, [key]: value })"
              />
            </tbody>
          </table>
          <div class="params-foot">
            <span class="hint">{{ limitHint(solverParams) }}</span>
            <button
              type="button"
              class="link"
              :disabled="!paramsChanged"
              @click="solverParams = { ...systemParams }"
            >
              Сбросить
            </button>
          </div>
        </template>
      </section>

      <!-- один пересчёт уже посчитан и не утверждён: пока он есть, часть бригад стоит -->
      <p v-if="pendingReplanId" class="warning">
        <span class="mark">!</span>
        <span>
          Пересчёт №{{ pendingReplanId }} уже посчитан и вступит в силу сам, в момент,
          на который посчитан. Пока этот момент не настал, бригады выезжают только туда, куда
          ведёт и он, а остальные стоят. Лучше закрыть это окно и дождаться его — или удалить,
          если он не нужен. Новый расчёт добавит ещё один пересчёт.
        </span>
      </p>

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

      <!-- пересчёт: бригады, выбившиеся из плана, — оператор уточняет по телефону время -->
      <section v-if="replanOf && waitingRoutes.length" class="waiting">
        <h4>Застряли на заявке: {{ waitingRoutes.length }}</h4>
        <p class="hint">
          Застрявшая бригада не уложится в норматив. Время подставлено с запасом — уточните его
          по телефону и поправьте: пересчёт посчитает бригаду свободной с него, а не с планового
          конца работы.
        </p>
        <article v-for="route in waitingRoutes" :key="route.engineer_id" class="waiting-row">
          <strong>{{ route.engineer_name }}</strong>
          <a v-if="route.phone" class="phone" :href="`tel:${route.phone}`">{{ route.phone }}</a>
          <span class="muted">{{ stuckText(route) }}</span>
          <label class="free-at">
            освободится в
            <TimeInput
              v-model="freeAt[route.engineer_id]"
              :aria-label="`когда освободится бригада ${route.engineer_name}`"
            />
          </label>
        </article>
      </section>

      <!-- заявки, которым не нашлось места, останутся невлезшими: по ним оператор решает
           отдельно — «Подобрать окна» или «Утвердить» у самого пересчёта -->
      <p v-if="replanOf" class="hint">
        Заявки, которым в пересчёте не найдётся места, останутся за ним невлезшими. По ним
        решают отдельно: «Подобрать окна» — второй расчёт с раскрытыми окнами, «Утвердить» —
        перенос на другой день или отмена.
      </p>

      <footer>
        <span class="hint">Заявки и смены берутся на {{ formatDay(planDate) }}</span>
        <div class="dialog-actions">
          <button class="primary" :disabled="building" @click="submit">
            {{ building ? 'Считаю…' : replanOf ? 'Пересчитать' : 'Рассчитать' }}
          </button>
          <button :disabled="building" @click="close">Отмена</button>
        </div>
      </footer>
    </div>
  </div>
</template>

<style scoped>
/* параметры решателя в диалоге: свёрнуты, пока не понадобятся */
.solver-block {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px 10px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
}

.solver-toggle {
  text-align: left;
  font-size: 13px;
}

.params-table {
  width: 100%;
  table-layout: fixed;
  font-size: 13px;
}

/* «Сбросить» — вровень с правым краем карандашей: отступ как у ячейки таблицы */
.params-foot {
  display: flex;
  gap: 12px;
  align-items: baseline;
  justify-content: space-between;
  padding-right: 10px;
}

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
.dialog.wide,
.dialog:has(.waiting) {
  width: min(760px, 94vw);
  max-height: 90vh;
  overflow: auto;
}

.waiting-row .muted {
  color: #64748b;
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
