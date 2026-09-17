<script setup>
import { computed, onMounted, ref, watch } from 'vue'

import DayPanel from '../components/DayPanel.vue'
import PlanBuildDialog from '../components/PlanBuildDialog.vue'
import PlanMap from '../components/PlanMap.vue'
import PlanRoutesPanel from '../components/PlanRoutesPanel.vue'
import PlansList from '../components/PlansList.vue'
import { usePlanFocus } from '../composables/usePlanFocus.js'
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
  dayCheck,
  approve,
  cancelApproval,
  selectEngineer,
} = usePlans()

// пришли из сравнения планов: открываем нужный план
const { takePlanId } = usePlanFocus()

// окно параметров расчёта: открывается по «Построить план», поля заполнены по умолчанию
const buildDialogOpen = ref(false)

async function startBuild(params) {
  buildDialogOpen.value = false
  await buildDayPlan(params)
}

// «Маршруты» — таблица маршрутов, «Карта» — те же маршруты линиями на карте и карточками рядом
const viewMode = ref('details')

// клик по маршруту в списке открывает карту с этим маршрутом
function showRouteOnMap(engineerId) {
  selectEngineer(engineerId)
  if (selectedEngineerId.value !== null) viewMode.value = 'map'
}

watch(selectedDay, () => {
  viewMode.value = 'details'
})

onMounted(async () => {
  await load()
  const planId = takePlanId()
  if (planId) await selectPlan(planId)
})
</script>

<template>
  <div class="workspace">
    <header class="workspace-title">
      <h1>Планы</h1>
      <p>Маршруты исполнителей на день · время московское</p>
    </header>

    <DayPanel :disabled="building" :summary="`планов на этот день ${plans.length}`" />

    <section class="plan-toolbar">
      <button class="primary" :disabled="!selectedDay || building" @click="buildDialogOpen = true">
        {{ building ? 'Считаю…' : 'Построить план' }}
      </button>
    </section>

    <PlanBuildDialog
      v-if="buildDialogOpen"
      :plan-date="selectedDay"
      :day-check="dayCheck"
      :building="building"
      @build="startBuild"
      @close="buildDialogOpen = false"
    />

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
        <PlansList
          :plans="plans"
          :selected-plan-id="selectedPlanId"
          :busy="building"
          :held-requests="dayCheck?.held_requests ?? []"
          @select="selectPlan"
          @remove="removePlan"
          @approve="approve"
          @cancel-approval="cancelApproval"
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
              Маршруты плана №{{ plan.id }}
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
              :beside-map="viewMode === 'map'"
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

.plans-block {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.plans-block h2 {
  margin: 0;
  font-size: 16px;
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
