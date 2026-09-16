<script setup>
import { onMounted } from 'vue'

import PlanMap from '../components/PlanMap.vue'
import PlanRoutesPanel from '../components/PlanRoutesPanel.vue'
import { usePlans } from '../composables/usePlans.js'
import { formatDay, moscowTimeOf } from '../utils/moscowTime.js'

const {
  days,
  selectedDay,
  plans,
  selectedPlanId,
  plan,
  references,
  selectedEngineerId,
  loadingDays,
  loadingPlan,
  building,
  errorMessage,
  errorDetails,
  noticeMessage,
  loadDays,
  loadPlans,
  selectPlan,
  buildDayPlan,
  selectEngineer,
} = usePlans()

const RUN_TYPE_LABELS = {
  optimized: 'оптимизированный',
  replanned: 'после перепланирования',
}

function planLabel(summary) {
  const solver = summary.solver ?? 'без решателя'
  return (
    `№${summary.id} · ${RUN_TYPE_LABELS[summary.run_type] ?? summary.run_type} · ${solver} · ` +
    `${moscowTimeOf(summary.created_at)} · назначено ${summary.assigned_count} из ` +
    `${summary.assigned_count + summary.unassigned_count}`
  )
}

onMounted(loadDays)
</script>

<template>
  <div class="workspace">
    <header class="workspace-title">
      <h1>Планы</h1>
      <p>Маршруты исполнителей на день · время московское</p>
    </header>

    <section class="plan-toolbar">
      <label class="field day-field">
        <span>День</span>
        <select v-model="selectedDay" :disabled="loadingDays || building" @change="loadPlans">
          <option v-for="day in days" :key="day.plan_date" :value="day.plan_date">
            {{ formatDay(day.plan_date) }} · активных заявок {{ day.active_requests }}
          </option>
        </select>
      </label>

      <button class="primary" :disabled="!selectedDay || building" @click="buildDayPlan">
        {{ building ? 'Строю план…' : 'Построить план' }}
      </button>

      <label v-if="plans.length" class="field plan-field">
        <span>План</span>
        <select :value="selectedPlanId" :disabled="building" @change="selectPlan(Number($event.target.value))">
          <option v-for="summary in plans" :key="summary.id" :value="summary.id">{{ planLabel(summary) }}</option>
        </select>
      </label>
    </section>

    <div v-if="errorMessage" class="message error">
      <strong>{{ errorMessage }}</strong>
      <ul v-if="errorDetails.length">
        <li v-for="(detail, index) in errorDetails" :key="index">{{ detail }}</li>
      </ul>
    </div>

    <p v-if="loadingDays" class="muted">Загружаю дни…</p>
    <p v-else-if="!days.length" class="muted">Нет активных заявок ни на один день — планировать нечего.</p>
    <p v-else-if="!plans.length && !building" class="muted">На этот день планов ещё нет — постройте первый.</p>
    <p v-else-if="loadingPlan && !plan" class="muted">Загружаю план…</p>

    <div v-if="plan" class="plan-view">
      <div class="map-area">
        <PlanMap :plan="plan" :selected-engineer-id="selectedEngineerId" @select-engineer="selectEngineer" />
      </div>
      <div class="panel-area">
        <PlanRoutesPanel
          :plan="plan"
          :references="references"
          :selected-engineer-id="selectedEngineerId"
          @select-engineer="selectEngineer"
        />
      </div>
    </div>

    <Transition name="toast">
      <div v-if="noticeMessage" class="toast" role="status">{{ noticeMessage }}</div>
    </Transition>
  </div>
</template>

<style scoped>
.plan-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 10px 12px;
}

.day-field {
  width: 280px;
}

.plan-field {
  width: 460px;
  max-width: 100%;
}

.plan-view {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 380px;
  gap: 14px;
  align-items: start;
}

.panel-area {
  max-height: max(480px, calc(100vh - 300px));
  overflow: auto;
  padding-right: 4px;
}

@media (max-width: 1000px) {
  .plan-view {
    grid-template-columns: 1fr;
  }

  .panel-area {
    max-height: none;
  }
}
</style>
