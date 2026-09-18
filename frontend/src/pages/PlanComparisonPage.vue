<script setup>
// Сравнение планов: два плана одного дня рядом и разница по метрикам.
// Клик по плану открывает его на вкладке «Планы» — подробности по заявкам и маршрутам там.
import { onMounted } from 'vue'

import ErrorMessage from '../components/ErrorMessage.vue'
import DayPanel from '../components/DayPanel.vue'
import { usePlanComparison } from '../composables/usePlanComparison.js'
import { usePlanFocus } from '../composables/usePlanFocus.js'
import { moscowTimeOf } from '../utils/moscowTime.js'
import { objectivePolicyLabel } from '../utils/planningPriorities.js'

const {
  plans,
  selectedIds,
  selectionIsFull,
  togglePlan,
  first,
  second,
  metrics,
  loading,
  errorMessage,
  errorDetails,
  load,
} = usePlanComparison()
const { openPlan } = usePlanFocus()

function format(value, digits) {
  return value === null || value === undefined ? '—' : value.toFixed(digits)
}

// «лучше» считаем со стороны второго плана: это тот, что выбран правее
function differenceClass(metric) {
  if (metric.difference === null || metric.difference === 0) return ''
  const better = metric.lessIsBetter ? metric.difference < 0 : metric.difference > 0
  return better ? 'better' : 'worse'
}

function differenceText(metric) {
  if (metric.difference === null) return '—'
  const sign = metric.difference > 0 ? '+' : ''
  return `${sign}${format(metric.difference, metric.digits)}`
}

onMounted(load)
</script>

<template>
  <div class="workspace">
    <header class="workspace-title">
      <h1>Сравнение планов</h1>
      <p>Два плана одного дня рядом · время московское</p>
    </header>

    <DayPanel :summary="`планов на этот день ${plans.length}`" />

    <ErrorMessage v-if="errorMessage" :message="errorMessage" :details="errorDetails" @close="errorMessage = ''" />

    <p v-if="loading" class="muted">Загружаю планы…</p>
    <p v-else-if="plans.length < 2" class="muted">
      На этот день нужно хотя бы два плана — постройте их на вкладке «Планы».
    </p>

    <template v-else>
      <!-- выбор планов: одна колонка с галочками, сравниваются ровно два отмеченных -->
      <div class="table-scroll">
        <table class="data-table">
          <thead>
            <tr>
              <th class="pick">Сравнить</th>
              <th>План</th>
              <th>Решатель</th>
              <th>Приоритеты</th>
              <th>Рассчитан</th>
              <th>Назначено</th>
              <th>Пробег, км</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="summary in plans"
              :key="summary.id"
              :class="{
                selected: selectedIds.includes(summary.id),
                muted: selectionIsFull && !selectedIds.includes(summary.id),
              }"
            >
              <td class="pick">
                <input
                  type="checkbox"
                  :checked="selectedIds.includes(summary.id)"
                  :disabled="selectionIsFull && !selectedIds.includes(summary.id)"
                  :title="
                    selectionIsFull && !selectedIds.includes(summary.id)
                      ? 'Сначала снимите отметку с одного из выбранных планов'
                      : 'Сравнить этот план'
                  "
                  :aria-label="`Сравнить план №${summary.id}`"
                  @change="togglePlan(summary.id)"
                />
              </td>
              <td class="number-cell">№{{ summary.id }}</td>
              <td>{{ summary.solver ?? '—' }}</td>
              <td>{{ objectivePolicyLabel(summary.objective_order) }}</td>
              <td class="nowrap">{{ moscowTimeOf(summary.created_at) }}</td>
              <td class="number-cell">{{ summary.assigned_count }}</td>
              <td class="number-cell">
                {{ summary.total_distance_km === null ? '—' : summary.total_distance_km.toFixed(1) }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <p v-if="!first || !second" class="muted">Отметьте два плана, чтобы увидеть разницу.</p>

      <p
        v-else-if="objectivePolicyLabel(first.objective_order) !== objectivePolicyLabel(second.objective_order)"
        class="message warning"
      >
        Планы построены с разными приоритетами. Метрики сравнимы, но решатели оптимизировали
        разные цели.
      </p>

      <div v-if="first && second" class="table-scroll">
        <table class="data-table">
          <thead>
            <tr>
              <th>Показатель</th>
              <th>
                <button class="link" :title="`Открыть план №${first.id}`" @click="openPlan(first.id)">
                  План №{{ first.id }} · {{ first.solver }} →
                </button>
              </th>
              <th>
                <button class="link" :title="`Открыть план №${second.id}`" @click="openPlan(second.id)">
                  План №{{ second.id }} · {{ second.solver }} →
                </button>
              </th>
              <th>Разница</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="metric in metrics" :key="metric.key">
              <td>{{ metric.label }}</td>
              <td class="number-cell">{{ format(metric.first, metric.digits) }}</td>
              <td class="number-cell">{{ format(metric.second, metric.digits) }}</td>
              <td :class="['number-cell', differenceClass(metric)]">{{ differenceText(metric) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>

<style scoped>
/* колонка выбора узкая: в ней только галочка */
.pick {
  width: 86px;
  text-align: center;
}

/* пока выбраны два плана, остальные приглушены: отметить их нельзя */
.data-table tbody tr.muted td {
  color: #94a3b8;
}

.better {
  color: #16a34a;
}

.worse {
  color: #dc2626;
}

.data-table th button.link {
  font-weight: 600;
}
</style>
