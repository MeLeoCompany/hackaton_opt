<script setup>
// Планы выбранного дня: общая информация строкой, клик выбирает план,
// у каждого — кнопка удаления, чтобы день можно было пересчитать заново.
// Над таблицей — цепочка дня: из чего вырос каждый расчёт. В самой таблице связей нет,
// иначе одно и то же читается дважды.
import { computed, ref } from 'vue'

import { formatDay, moscowShortDateTimeOf, moscowTimeOf } from '../utils/moscowTime.js'
import { objectiveGoalLabel } from '../utils/planningPriorities.js'
import { planBlocked, planWindowOf } from '../utils/planWindow.js'
import { useSystemTime } from '../composables/useSystemTime.js'
import PlanGraph from './PlanGraph.vue'
import ReplanMark from './ReplanMark.vue'
import { isApproximate, providerTitle } from '../utils/routeProvider.js'

const props = defineProps({
  plans: { type: Array, required: true },
  selectedPlanId: { type: Number, default: null },
  busy: { type: Boolean, default: false },
  // заявки дня, занятые утверждённым планом другого дня — о них предупреждаем у каждой строки
  heldRequests: { type: Array, default: () => [] },
  // план, чья плашка «стоит пересчитать» открыта: его «Пересчитать» подсвечена
  attentionPlanId: { type: Number, default: null },
  // а если пересчёт уже посчитан — подсвечено «Утвердить» у самого пересчёта
  attentionReplanId: { type: Number, default: null },
})
defineEmits([
  'select',
  'remove',
  'approve',
  'pick-windows',
  'cancel-approval',
  'replan-info',
  'replan',
])

// одно и то же предупреждение для всех планов дня: их считали без этих заявок
const heldWarning = computed(() => {
  if (!props.heldRequests.length) return ''
  const holders = [...new Set(props.heldRequests.map((held) => `№${held.plan_id} от ${formatDay(held.plan_date)}`))]
  const numbers = props.heldRequests.map((held) => `№${held.request_id}`).join(', ')
  return (
    `Заявок этого дня закреплено за утверждёнными планами других дней: ${props.heldRequests.length} ` +
    `(${numbers}). Забрали: ${holders.join(', ')}. В расчёт этого дня они не идут — ` +
    'чтобы одну заявку не выполнили дважды.'
  )
})

// часы сервера идут сами: по ним считается, сколько осталось до вступления пересчёта в силу
// и сколько — до конца жизни черновика
const { now } = useSystemTime()

// срок расчёта: у пересчёта — когда он вступит в силу, у черновика — до когда его утверждать
function planWindow(summary) {
  return planWindowOf(summary, now.value)
}

function blocked(summary) {
  return planBlocked(summary, now.value)
}

// Как расчёты дня выросли друг из друга — строкой над таблицей. Сама таблица плоская:
// расчёты по времени, новые сверху (docs/algoV2.md, шаг 6)
// отладочные колонки: решатель, цели, пробег и время расчёта — по галочке над таблицей
const detailed = ref(false)

// действующий план дня: пока он есть, другой план дня утвердить нельзя — только пересчитать его
const workingPlan = computed(() => props.plans.find((plan) => plan.approved_at && !plan.superseded_at) ?? null)

function approveBlockedBy(summary) {
  const working = workingPlan.value
  return !working || summary.parent_plan_id === working.id ? null : working
}

// пересчёт вступает в силу сам в свой момент; кнопка — применить его раньше, руками
function approveTitle(summary) {
  if (!summary.parent_plan_id) return 'Утвердить план: его заявки закрепятся за этим днём'
  return (
    `Применить пересчёт сейчас, не дожидаясь ${moscowTimeOf(summary.replanned_at)}: он сразу ` +
    'заменит действующий план, и бригады увидят новый маршрут. Если не нажимать, он вступит ' +
    'в силу сам в этот момент'
  )
}

// расчёт не удержал обещанное клиенту время — до утверждения это видно (docs/algoV2.md, шаг 5)
function promiseWarning(summary) {
  if (!summary.broken_promises?.length) return ''
  const lines = summary.broken_promises.map((promise) => {
    const promised = `${moscowTimeOf(promise.promised_from)}–${moscowTimeOf(promise.promised_to)}`
    const fact = promise.planned_start ? `план ставит ${moscowTimeOf(promise.planned_start)}` : 'в план не попала'
    return `№${promise.request_id}: обещали ${promised}, ${fact}`
  })
  return `Обещания клиентам не удержаны:\n${lines.join('\n')}`
}

function distanceLabel(summary) {
  if (summary.total_distance_km === null) return '—'
  return `${isApproximate(summary.distance_provider) ? '≈ ' : ''}${summary.total_distance_km.toFixed(1)}`
}

function distanceTitle(summary) {
  return providerTitle(summary.distance_provider)
}

function solveDuration(summary) {
  return summary.solve_duration_ms === null ? '—' : `${summary.solve_duration_ms.toFixed(1)} мс`
}

// что стало с расчётом — ровно одна плашка на строку. Откуда он взялся, видно строкой выше
// и по ветке; беды его пересчётов — по «!» у номера
function fate(summary) {
  if (summary.superseded_at) {
    return {
      text: `заменён в ${moscowTimeOf(summary.superseded_at)}`,
      cls: 'superseded',
      title: 'Заменён утверждённым пересчётом: бригады ездят по новому',
    }
  }
  if (summary.approved_at) {
    return {
      text: `действует с ${moscowTimeOf(summary.approved_at)}`,
      cls: 'approved',
      title: 'Заявки этого плана закреплены за днём',
    }
  }
  if (summary.voided_at) {
    return {
      text: `не вступил в силу в ${moscowTimeOf(summary.voided_at)}`,
      cls: 'takes-effect voided',
      title: summary.void_reason ?? 'За время расчёта день изменился — посчитайте заново',
    }
  }
  const window = planWindow(summary)
  if (window) return { text: window.text, cls: `takes-effect ${window.state}`, title: window.title }
  if (summary.outdated) {
    return {
      text: 'черновик · неактуален',
      cls: 'plain',
      title: 'На этот день действует другой план — этот расчёт уже не утвердить. Он остаётся в истории дня',
    }
  }
  return { text: 'черновик', cls: 'plain', title: 'Расчёт посчитан, но не утверждён' }
}

// откуда расчёт вырос — подсказкой к строке происхождения
function originTitle(summary) {
  const parts = []
  if (summary.parent_plan_id) {
    parts.push(`Пересчёт плана №${summary.parent_plan_id} на ${moscowTimeOf(summary.replanned_at)}`)
  }
  if (summary.decisions_from_plan_id) {
    parts.push(
      `Учтены решения по заявкам, не вошедшим в расчёт №${summary.decisions_from_plan_id}: ` +
        `${summary.decisions_count ?? ''}`,
    )
  }
  return parts.join('. ') || 'Первый расчёт дня'
}
</script>

<template>
  <div class="plans-table">
    <div class="table-top">
      <!-- из чего что выросло: слева направо по времени, действующий план в первой строке -->
      <PlanGraph
        :plans="plans"
        :selected-plan-id="selectedPlanId"
        @select="$emit('select', $event)"
      />
    </div>

    <div class="table-scroll">
      <table class="data-table">
        <thead>
          <tr>
            <th>№</th>
            <th>Рассчитан</th>
            <th v-if="detailed">Решатель</th>
            <th v-if="detailed">Цели</th>
            <th>Назначено</th>
            <th title="Аварийных заявок в плане">Авар.</th>
            <th title="Заявок, которым не нашлось места">Не назн.</th>
            <th>Бригад</th>
            <th v-if="detailed" title="Общий пробег по дорогам, км">Пробег</th>
            <th v-if="detailed">Расчёт</th>
            <th>Состояние</th>
            <th class="tools-head">
              <label class="details-toggle" title="Решатель, цели, пробег и время расчёта — нужны при сравнении алгоритмов">
                <input v-model="detailed" type="checkbox" />
                Подробности
              </label>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="summary in plans"
            :key="summary.id"
            :class="{ selected: summary.id === selectedPlanId }"
            @click="$emit('select', summary.id)"
          >
            <td class="number-cell nowrap">
              {{ summary.id }}
              <ReplanMark :summary="summary" @show="$emit('replan-info', summary.id)" />
              <span v-if="heldWarning" class="held-warning" :title="heldWarning">!</span>
              <span v-if="promiseWarning(summary)" class="promise-warning" :title="promiseWarning(summary)">☎</span>
            </td>
            <td class="nowrap">{{ moscowShortDateTimeOf(summary.created_at) }}</td>
            <td v-if="detailed" class="nowrap">{{ summary.solver ?? '—' }}</td>
            <td v-if="detailed" class="goal-cell">{{ objectiveGoalLabel(summary.objective_order) }}</td>
            <td class="number-cell">{{ summary.assigned_count }}</td>
            <td class="number-cell">{{ summary.urgent_assigned_count ?? '—' }}</td>
            <td class="number-cell">{{ summary.unassigned_count }}</td>
            <td class="number-cell">{{ summary.engineers_used }}</td>
            <td v-if="detailed" class="number-cell" :title="distanceTitle(summary)">{{ distanceLabel(summary) }}</td>
            <td v-if="detailed" class="number-cell nowrap">{{ solveDuration(summary) }}</td>
            <!-- что стало с расчётом; из чего он вырос — в цепочке над таблицей -->
            <td class="state-cell" :title="originTitle(summary)">
              <span class="fate">
                <span :class="['badge', fate(summary).cls]" :title="fate(summary).title">
                  {{ fate(summary).text }}
                </span>
                <button
                  v-if="summary.replaced_by_plan_id"
                  class="link plan-link"
                  :title="`Открыть пересчёт №${summary.replaced_by_plan_id}, который его заменил`"
                  @click.stop="$emit('select', summary.replaced_by_plan_id)"
                >
                  → №{{ summary.replaced_by_plan_id }}
                </button>
              </span>
            </td>
            <td>
              <!-- заменённый план — история: по нему уже не ездят, действий нет -->
              <div v-if="summary.superseded_at" class="row-actions"></div>
              <div v-else class="row-actions">
                <button
                  v-if="summary.approved_at"
                  :class="['primary', { 'attention-pulse': summary.id === attentionPlanId && !summary.pending_replan_id }]"
                  :disabled="busy"
                  title="Пересчитать остаток дня с текущего момента: выполненное и начатое остаётся за бригадами"
                  @click.stop="$emit('replan', summary)"
                >
                  Пересчитать
                </button>
                <!-- по плану, который бригады уже видят в приложении, утверждение не снимают:
                     маршрут пропал бы у едущей бригады. Менять его можно только пересчётом -->
                <button
                  v-if="summary.can_cancel_approval"
                  :disabled="busy"
                  title="Снять утверждение: заявки станут доступны другим дням"
                  @click.stop="$emit('cancel-approval', summary)"
                >
                  Снять
                </button>
                <!-- второй расчёт с раскрытыми окнами: пробуем вместить невлезшие сегодня.
                     Отдельной кнопкой, потому что это новый расчёт дня, а не утверждение.
                     Одинаково у черновика и у пересчёта: круг и решения в нём одни и те же -->
                <button
                  v-if="!summary.approved_at && !summary.pending_offers && summary.unassigned_count"
                  :disabled="busy || Boolean(approveBlockedBy(summary)) || blocked(summary)"
                  :title="
                    blocked(summary)
                      ? planWindow(summary).title
                      : 'Подобрать время невлезшим заявкам: второй расчёт с раскрытыми окнами — что предложить клиентам'
                  "
                  @click.stop="$emit('pick-windows', summary)"
                >
                  Подобрать окна
                </button>
                <button
                  v-if="!summary.approved_at"
                  :class="{ 'attention-pulse': summary.id === attentionReplanId }"
                  :disabled="
                    busy || Boolean(approveBlockedBy(summary)) || blocked(summary) ||
                      Boolean(summary.hold_reason)
                  "
                  :title="
                    blocked(summary)
                      ? planWindow(summary).title
                      : summary.hold_reason
                        ? summary.hold_reason
                        : approveBlockedBy(summary)
                          ? `На этот день действует план №${approveBlockedBy(summary).id} — его можно пересчитать, а этот расчёт остаётся черновиком`
                          : approveTitle(summary)
                  "
                  @click.stop="$emit('approve', summary)"
                >
                  {{ summary.parent_plan_id ? 'Применить' : 'Утвердить' }}
                </button>
                <button
                  v-if="!summary.approved_at"
                  class="danger"
                  :disabled="busy"
                  @click.stop="$emit('remove', summary)"
                >
                  Удалить
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
/* предупреждение у каждой строки: план считался без заявок, занятых другим днём */
/* сорванные обещания: оператор решает, утверждать или оставить прежний план */
.promise-warning {
  margin-left: 4px;
  color: #b91c1c;
  font-size: 13px;
  cursor: help;
}

/* цель расчёта переносится по словам: колонка иначе растягивает таблицу за экран */
.goal-cell {
  max-width: 96px;
}

/* кнопки строки одного размера: «Пересчитать» длиннее остальных и выбивалась из ряда */
.row-actions button {
  min-width: 116px;
}

/* отладочные колонки нужны не всегда: показываем по галочке */
.details-toggle {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin: 0;
  color: #64748b;
  font-size: 12px;
  font-weight: 400;
  cursor: pointer;
  white-space: nowrap;
}

/* цепочка дня над таблицей: из чего что выросло */
.table-top {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  gap: 4px 16px;
  margin-bottom: 6px;
}

.chains {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.day-chain {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 4px;
  font-size: 12px;
}

.chain-title {
  color: #64748b;
}

.chain-arrow {
  color: #94a3b8;
  white-space: nowrap;
}

.chain-when {
  margin-right: 4px;
  color: #64748b;
}

.day-chain .plan-link {
  margin-left: 0;
  font-size: 12px;
}

.day-chain .plan-link.current {
  font-weight: 700;
}

/* галочка живёт в шапке таблицы, над кнопками строк: рядом с графом она путалась с ним */
.tools-head {
  text-align: right;
  font-weight: 400;
}

.fate {
  display: flex;
  align-items: center;
  gap: 4px;
}

.badge.plain {
  padding: 0;
  background: none;
  color: #64748b;
}

/* ссылки на соседние планы дня: родителя пересчёта и пересчёт, который заменил этот план */
.plan-link {
  margin-left: 6px;
  font-size: 12px;
}

/* кнопки строки всегда на виду: таблица шире экрана, и они уезжали за правый край */
.data-table th:last-child,
.data-table td:last-child {
  position: sticky;
  right: 0;
  background: #fff;
  box-shadow: -6px 0 6px -6px rgb(15 23 42 / 25%);
}

.data-table thead th:last-child {
  background: #f8fafc;
}

.data-table tr.selected td:last-child {
  background: #fef9c3;
}

/* судьба плана: откуда он и что с ним стало */
.state-cell {
  min-width: 150px;
  font-size: 12px;
  line-height: 1.5;
}

.held-warning {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  margin-left: 6px;
  border-radius: 50%;
  background: #f59e0b;
  color: #fff;
  font-size: 11px;
  font-weight: 700;
  cursor: help;
}

.badge.superseded {
  background: #f1f5f9;
  color: #64748b;
}

/* пересчёт ждёт утверждения: когда он вступит в силу и сколько на это осталось */
.badge.takes-effect {
  background: #eef2ff;
  color: #3730a3;
}

/* подбор окон ждёт ответов клиентов: это ещё не план */
.badge.takes-effect.offers {
  background: #fef3c7;
  color: #92400e;
}

.badge.takes-effect.now {
  background: #fef3c7;
  color: #92400e;
}

.badge.takes-effect.voided,
.badge.takes-effect.expired {
  background: #fee2e2;
  color: #991b1b;
}

.badge.approved {
  background: #dcfce7;
  color: #166534;
}
</style>
