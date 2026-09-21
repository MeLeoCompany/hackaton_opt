<script setup>
// Планы выбранного дня: общая информация строкой, клик выбирает план,
// у каждого — кнопка удаления, чтобы день можно было пересчитать заново.
import { computed } from 'vue'

import { formatDay, moscowTimeOf } from '../utils/moscowTime.js'
import { objectiveGoalLabel } from '../utils/planningPriorities.js'
import ReplanMark from './ReplanMark.vue'
import { isApproximate, providerTitle } from '../utils/routeProvider.js'

const props = defineProps({
  plans: { type: Array, required: true },
  selectedPlanId: { type: Number, default: null },
  busy: { type: Boolean, default: false },
  // заявки дня, занятые утверждённым планом другого дня — о них предупреждаем у каждой строки
  heldRequests: { type: Array, default: () => [] },
})
defineEmits(['select', 'remove', 'approve', 'cancel-approval', 'replan-info', 'replan'])

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

// действующий план дня: пока он есть, другой план дня утвердить нельзя — только пересчитать его
const workingPlan = computed(() => props.plans.find((plan) => plan.approved_at && !plan.superseded_at) ?? null)

function approveBlockedBy(summary) {
  const working = workingPlan.value
  return !working || summary.parent_plan_id === working.id ? null : working
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
</script>

<template>
  <div class="table-scroll">
    <table class="data-table">
      <thead>
        <tr>
          <th>№</th>
          <th>Рассчитан</th>
          <th>Решатель</th>
          <th>Цели</th>
          <th>Назначено</th>
          <th title="Аварийных заявок в плане">Авар.</th>
          <th title="Заявок, которым не нашлось места">Не назн.</th>
          <th>Бригад</th>
          <th>Пробег, км</th>
          <th>Расчёт</th>
          <th>Состояние</th>
          <th></th>
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
          <td class="nowrap">{{ moscowTimeOf(summary.created_at) }}</td>
          <td class="nowrap">{{ summary.solver ?? '—' }}</td>
          <td class="nowrap">{{ objectiveGoalLabel(summary.objective_order) }}</td>
          <td class="number-cell">{{ summary.assigned_count }}</td>
          <td class="number-cell">{{ summary.urgent_assigned_count ?? '—' }}</td>
          <td class="number-cell">{{ summary.unassigned_count }}</td>
          <td class="number-cell">{{ summary.engineers_used }}</td>
          <td class="number-cell" :title="distanceTitle(summary)">{{ distanceLabel(summary) }}</td>
          <td class="number-cell nowrap">{{ solveDuration(summary) }}</td>
          <!-- одна колонка про судьбу плана: чей это пересчёт, действует ли он и кем заменён -->
          <td class="state-cell">
            <span v-if="summary.parent_plan_id" class="replan-of">
              пересчёт
              <button class="link plan-link" @click.stop="$emit('select', summary.parent_plan_id)">
                №{{ summary.parent_plan_id }}
              </button>
              на {{ moscowTimeOf(summary.replanned_at) }}
            </span>
            <!-- черновик пересчитан после обзвона клиентов невлезших заявок другого черновика -->
            <span
              v-if="summary.decisions_from_plan_id"
              class="replan-of"
              :title="`Учтены решения по заявкам, не вошедшим в черновик №${summary.decisions_from_plan_id}: ${summary.decisions_count}`"
            >
              с решениями из
              <button class="link plan-link" @click.stop="$emit('select', summary.decisions_from_plan_id)">
                №{{ summary.decisions_from_plan_id }}
              </button>
            </span>
            <span
              v-if="summary.superseded_at"
              class="badge superseded"
              :title="`Заменён утверждённым пересчётом в ${moscowTimeOf(summary.superseded_at)}: бригады ездят по новому`"
            >
              заменён в {{ moscowTimeOf(summary.superseded_at) }}
            </span>
            <button
              v-if="summary.replaced_by_plan_id"
              class="link plan-link"
              :title="`Открыть пересчёт №${summary.replaced_by_plan_id}, который его заменил`"
              @click.stop="$emit('select', summary.replaced_by_plan_id)"
            >
              → №{{ summary.replaced_by_plan_id }}
            </button>
            <span v-else-if="summary.approved_at" class="badge approved" title="Заявки этого плана закреплены за днём">
              действует с {{ moscowTimeOf(summary.approved_at) }}
            </span>
            <span v-else class="muted">черновик</span>
          </td>
          <td>
            <!-- заменённый план — история: по нему уже не ездят, действий нет -->
            <div v-if="summary.superseded_at" class="row-actions"></div>
            <div v-else class="row-actions">
              <button
                v-if="summary.approved_at"
                class="primary"
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
              <button
                v-if="!summary.approved_at"
                :disabled="busy || Boolean(approveBlockedBy(summary))"
                :title="
                  approveBlockedBy(summary)
                    ? `На этот день действует план №${approveBlockedBy(summary).id} — его можно пересчитать, а этот расчёт остаётся черновиком`
                    : 'Утвердить план: его заявки закрепятся за этим днём'
                "
                @click.stop="$emit('approve', summary)"
              >
                Утвердить
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

/* судьба плана: пересчёт чего он, действует ли, кем заменён */
.state-cell {
  min-width: 170px;
  font-size: 12px;
  line-height: 1.5;
}

.state-cell .replan-of {
  display: block;
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

/* пересчёт с момента: под названием решателя */
.replan-of {
  display: block;
  color: #64748b;
  font-size: 12px;
}

.badge.superseded {
  background: #f1f5f9;
  color: #64748b;
}

.badge.approved {
  background: #dcfce7;
  color: #166534;
}
</style>
