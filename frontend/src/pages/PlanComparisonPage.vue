<script setup>
// Сравнение планов: два плана одного дня рядом и разница по метрикам.
// Клик по плану открывает его на вкладке «Планы» — подробности по заявкам и маршрутам там.
import { onMounted } from 'vue'

import DayPanel from '../components/DayPanel.vue'
import { usePlanComparison } from '../composables/usePlanComparison.js'
import { usePlanFocus } from '../composables/usePlanFocus.js'
import { moscowTimeOf } from '../utils/moscowTime.js'

const {
  plans,
  firstId,
  secondId,
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

    <div v-if="errorMessage" class="message error">
      <strong>{{ errorMessage }}</strong>
      <ul v-if="errorDetails.length">
        <li v-for="(detail, index) in errorDetails" :key="index">{{ detail }}</li>
      </ul>
    </div>

    <p v-if="loading" class="muted">Загружаю планы…</p>
    <p v-else-if="plans.length < 2" class="muted">
      На этот день нужно хотя бы два плана — постройте их на вкладке «Планы».
    </p>

    <template v-else>
      <!-- выбор планов списком: сразу видно, чем они отличаются, и не нужно читать длинные подписи -->
      <div class="table-scroll">
        <table class="data-table">
          <thead>
            <tr>
              <th class="pick">А</th>
              <th class="pick">Б</th>
              <th>План</th>
              <th>Решатель</th>
              <th>Рассчитан</th>
              <th>Назначено</th>
              <th>Пробег, км</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="summary in plans"
              :key="summary.id"
              :class="{ selected: summary.id === firstId || summary.id === secondId }"
            >
              <td class="pick">
                <input
                  v-model="firstId"
                  type="radio"
                  name="first-plan"
                  :value="summary.id"
                  :disabled="summary.id === secondId"
                  :aria-label="`План №${summary.id} как А`"
                />
              </td>
              <td class="pick">
                <input
                  v-model="secondId"
                  type="radio"
                  name="second-plan"
                  :value="summary.id"
                  :disabled="summary.id === firstId"
                  :aria-label="`План №${summary.id} как Б`"
                />
              </td>
              <td class="number-cell">№{{ summary.id }}</td>
              <td>{{ summary.solver ?? '—' }}</td>
              <td class="nowrap">{{ moscowTimeOf(summary.created_at) }}</td>
              <td class="number-cell">{{ summary.assigned_count }}</td>
              <td class="number-cell">
                {{ summary.total_distance_km === null ? '—' : summary.total_distance_km.toFixed(1) }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

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
/* колонки выбора узкие: в них только переключатель */
.pick {
  width: 34px;
  text-align: center;
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
