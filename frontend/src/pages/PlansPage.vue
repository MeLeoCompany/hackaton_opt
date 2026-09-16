<script setup>
import { onMounted, ref, watch } from 'vue'

import DayPanel from '../components/DayPanel.vue'
import PlanMap from '../components/PlanMap.vue'
import PlanRoutesPanel from '../components/PlanRoutesPanel.vue'
import PlansList from '../components/PlansList.vue'
import { usePlans } from '../composables/usePlans.js'
import { formatDay } from '../utils/moscowTime.js'

const {
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
  load,
  loadPlans,
  selectPlan,
  buildDayPlan,
  removePlan,
  selectEngineer,
} = usePlans()

// «Характеристики» — сводка и маршруты списком, «Карта» — те же маршруты линиями на карте
const viewMode = ref('details')

// клик по маршруту в списке открывает карту с этим маршрутом
function showRouteOnMap(engineerId) {
  selectEngineer(engineerId)
  if (selectedEngineerId.value !== null) viewMode.value = 'map'
}

watch(selectedDay, () => {
  viewMode.value = 'details'
})

onMounted(load)
</script>

<template>
  <div class="workspace">
    <header class="workspace-title">
      <h1>Планы</h1>
      <p>Маршруты исполнителей на день · время московское</p>
    </header>

    <DayPanel :disabled="building" :summary="`планов на этот день ${plans.length}`" />

    <section class="plan-toolbar">
      <button class="primary" :disabled="!selectedDay || building" @click="buildDayPlan">
        {{ building ? 'Строю план…' : 'Построить план на ' + formatDay(selectedDay) }}
      </button>
    </section>

    <div v-if="errorMessage" class="message error">
      <strong>{{ errorMessage }}</strong>
      <ul v-if="errorDetails.length">
        <li v-for="(detail, index) in errorDetails" :key="index">{{ detail }}</li>
      </ul>
    </div>

    <p v-if="loadingDays" class="muted">Загружаю планы…</p>

    <template v-else>
      <p v-if="!plans.length && !building" class="muted">На этот день планов ещё нет — постройте первый.</p>

      <section v-else class="plans-block">
        <h2>Планы на {{ formatDay(selectedDay) }} · {{ plans.length }}</h2>
        <p class="muted">Клик по строке открывает план: характеристики, маршруты и карту</p>
        <PlansList
          :plans="plans"
          :selected-plan-id="selectedPlanId"
          :busy="building"
          @select="selectPlan"
          @remove="removePlan"
        />
      </section>

      <p v-if="loadingPlan && !plan" class="muted">Загружаю план…</p>

      <template v-if="plan">
        <div class="list-bar">
          <div class="view-switch" role="tablist">
            <button
              role="tab"
              :aria-selected="viewMode === 'details'"
              :class="{ active: viewMode === 'details' }"
              @click="viewMode = 'details'"
            >
              Характеристики плана №{{ plan.id }}
            </button>
            <button
              role="tab"
              :aria-selected="viewMode === 'map'"
              :class="{ active: viewMode === 'map' }"
              @click="viewMode = 'map'"
            >
              Карта плана №{{ plan.id }} · маршрутов {{ plan.routes.length }}
            </button>
          </div>
        </div>

        <div :class="['plan-view', { 'with-map': viewMode === 'map' }]">
          <div v-if="viewMode === 'map'" class="map-area">
            <PlanMap :plan="plan" :selected-engineer-id="selectedEngineerId" @select-engineer="selectEngineer" />
          </div>
          <div class="panel-area">
            <PlanRoutesPanel
              :plan="plan"
              :references="references"
              :selected-engineer-id="selectedEngineerId"
              :with-characteristics="viewMode === 'details'"
              @select-engineer="viewMode === 'details' ? showRouteOnMap($event) : selectEngineer($event)"
            />
          </div>
        </div>
      </template>
    </template>

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

.plans-block {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.plans-block h2 {
  margin: 0;
  font-size: 16px;
}

.plans-block p {
  margin: 0;
}

.plan-view {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 14px;
  align-items: start;
}

.plan-view.with-map {
  grid-template-columns: minmax(0, 1fr) 380px;
}

.plan-view.with-map .panel-area {
  max-height: max(480px, calc(100vh - 380px));
  overflow: auto;
  padding-right: 4px;
}

@media (max-width: 1000px) {
  .plan-view.with-map {
    grid-template-columns: 1fr;
  }

  .plan-view.with-map .panel-area {
    max-height: none;
  }
}
</style>
