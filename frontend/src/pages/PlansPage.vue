<script setup>
import { computed, onMounted, ref, watch } from 'vue'

import ErrorMessage from '../components/ErrorMessage.vue'
import DayPanel from '../components/DayPanel.vue'
import IconButton from '../components/IconButton.vue'
import PlanApprovalDialog from '../components/PlanApprovalDialog.vue'
import PlanBuildDialog from '../components/PlanBuildDialog.vue'
import PlanMap from '../components/PlanMap.vue'
import PlanRoutesPanel from '../components/PlanRoutesPanel.vue'
import PlansList from '../components/PlansList.vue'
import ReplanMark from '../components/ReplanMark.vue'
import ReplanNotice from '../components/ReplanNotice.vue'
import PlanRunProgress from '../components/PlanRunProgress.vue'
import { usePlanFocus } from '../composables/usePlanFocus.js'
import { usePlanRun } from '../composables/usePlanRun.js'
import { useSystemTime } from '../composables/useSystemTime.js'
import { usePlans } from '../composables/usePlans.js'
import { formatDay, moscowTimeOf } from '../utils/moscowTime.js'
import { planChain } from '../utils/planChain.js'

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
  closePlan,
  buildDayPlan,
  removePlan,
  dayCheck,
  approve,
  decideApproval,
  cancelApproval,
  replan,
  selectEngineer,
  markVisitStatus,
  allowDeparture,
  syncing,
  syncRoutes,
} = usePlans()


// пересчёт утверждённого плана с момента: окно параметров с временем пересчёта
const replanTarget = ref(null)
// маршруты пересчитываемого плана, если он открыт: в диалоге по ним видно, кто выбился из плана
const replanRoutes = computed(() =>
  plan.value && plan.value.id === replanTarget.value?.id ? plan.value.routes : [],
)

async function startReplan(params) {
  const summary = replanTarget.value
  replanTarget.value = null
  replanPlanId.value = null
  await withRunLog(params, () => replan(summary, params))
  // открыт план — возвращаемся к списку: там рядом старый план и его пересчёт
  if (selectedPlanId.value !== null) backToPlans()
}

// ход расчёта: номер запуска придумываем здесь, по нему журнал показывает шаги и проценты
const { run: planRun, newRunId, watch: watchRun, cancel: cancelRun, stop: stopRun } = usePlanRun()

async function withRunLog(params, action) {
  params.run_id = newRunId()
  watchRun(params.run_id)
  try {
    await action()
  } finally {
    stopRun()
  }
}

// утверждение черновика, в который вошли не все заявки: сначала предлагаем подобрать окна
const approvalTarget = ref(null)

function requestApproval(summary) {
  if (!summary.parent_plan_id && summary.unassigned_count > 0) approvalTarget.value = summary
  else approve(summary)
}

function approveAsIs() {
  const summary = approvalTarget.value
  approvalTarget.value = null
  approve(summary)
}

async function startDecisions(params) {
  const summary = approvalTarget.value
  approvalTarget.value = null
  await withRunLog(params, () => decideApproval(summary, params))
}

// пришли из сравнения планов: открываем нужный план; из заявки — ещё и её точку на карте
const { takePlanId, takePlanRequestId } = usePlanFocus()
// заявка, выделенная на карте плана; null — ничего не выделено
const focusedRequestId = ref(null)

// окно параметров расчёта: открывается по «Построить план», поля заполнены по умолчанию
const buildDialogOpen = ref(false)

async function startBuild(params) {
  buildDialogOpen.value = false
  await withRunLog(params, () => buildDayPlan(params))
}

// «Маршруты» — таблица маршрутов, «Карта» — те же маршруты линиями на карте и карточками рядом
const viewMode = ref('details')

// Страница в двух состояниях: список планов дня или маршруты одного плана.
// Клик по плану в списке открывает его маршруты, стрелка «← Планы на …» возвращает к списку.
const planOpened = computed(() => selectedPlanId.value !== null)

// сводка открытого плана — та же строка, что в списке: чтобы было видно, что за план
const openedSummary = computed(() => plans.value.find((summary) => summary.id === selectedPlanId.value) ?? null)
// режим демонстрации: у действующего утверждённого плана маршруты можно привести к плану
const { demoMode } = useSystemTime()
const syncable = computed(
  () => demoMode.value && Boolean(openedSummary.value?.approved_at) && !openedSummary.value?.superseded_at,
)
// отмеченные маршруты — по бригадам; сменили план — отметки не переносятся
const syncSelected = ref([])
watch(selectedPlanId, () => {
  syncSelected.value = []
})

async function syncChosen() {
  await syncRoutes(syncSelected.value)
}
// исходный план дня и его пересчёты по порядку: видно, что происходило за день
const openedChain = computed(() => planChain(plans.value, selectedPlanId.value))

// «что не так» с утверждённым планом — открывается по клику на его «!»
const replanPlanId = ref(null)
const replanSummary = computed(() => plans.value.find((summary) => summary.id === replanPlanId.value) ?? null)

function openPlan(planId) {
  viewMode.value = 'details'
  focusedRequestId.value = null
  selectPlan(planId)
}

// чем этот план кончился: когда его заменили, что он действует или ещё ждёт утверждения
function chainWhen(summary) {
  if (summary.superseded_at) return `до ${moscowTimeOf(summary.superseded_at)}`
  if (summary.approved_at) return 'действует'
  return 'не утверждён'
}

function backToPlans() {
  closePlan()
  focusedRequestId.value = null
  viewMode.value = 'details'
}

function routeOfRequest(requestId) {
  return plan.value?.routes.find((item) => item.visits.some((visit) => visit.request_id === requestId)) ?? null
}

// пришли из заявки: карта с маршрутом бригады, которая к ней едет, и выделенной точкой
function focusRequest(requestId) {
  focusedRequestId.value = requestId
  selectedEngineerId.value = routeOfRequest(requestId)?.engineer_id ?? null
  viewMode.value = 'map'
}

// кликнули по другому визиту — в карточке или точкой на карте: подсветка переходит на него.
// Если на карте показан один маршрут, а визит из другого — показываем маршрут этого визита.
// null — клик по пустому месту карты: подсветку снимаем, маршрут остаётся
function focusVisit(requestId) {
  focusedRequestId.value = requestId
  if (requestId === null || selectedEngineerId.value === null) return
  selectedEngineerId.value = routeOfRequest(requestId)?.engineer_id ?? null
}

// клик по маршруту в списке открывает карту с этим маршрутом
function showRouteOnMap(engineerId) {
  selectEngineer(engineerId)
  if (selectedEngineerId.value !== null) viewMode.value = 'map'
}

// сменили день — снова список планов этого дня
watch(selectedDay, () => {
  viewMode.value = 'details'
  replanPlanId.value = null
})

onMounted(async () => {
  await load()
  const planId = takePlanId()
  const requestId = takePlanRequestId()
  if (planId) {
    await selectPlan(planId)
    if (requestId !== null && plan.value) focusRequest(requestId)
  }
})
</script>

<template>
  <div class="workspace">
    <!-- заголовок на одном месте: «Планы» в списке, «План №…» в открытом плане -->
    <header class="workspace-title">
      <template v-if="!planOpened">
        <h1>Планы</h1>
        <p>Маршруты исполнителей на день · время московское</p>
      </template>
      <template v-else>
        <h1 class="plan-title">
          План №{{ selectedPlanId }}
          <ReplanMark :summary="openedSummary" large @show="replanPlanId = selectedPlanId" />
          <span v-if="openedSummary?.superseded_at" class="badge superseded" title="Бригады ездят по утверждённому пересчёту">
            заменён в {{ moscowTimeOf(openedSummary.superseded_at) }}
          </span>
          <span v-else-if="openedSummary?.approved_at" class="badge approved">утверждён</span>
          <span v-if="openedSummary?.parent_plan_id" class="replan-title">
            пересчёт плана
            <button class="link plan-link" @click="openPlan(openedSummary.parent_plan_id)">
              №{{ openedSummary.parent_plan_id }}
            </button>
            на {{ moscowTimeOf(openedSummary.replanned_at) }}
          </span>
          <span v-if="openedSummary?.replaced_by_plan_id" class="replan-title">
            заменён пересчётом
            <button class="link plan-link" @click="openPlan(openedSummary.replaced_by_plan_id)">
              №{{ openedSummary.replaced_by_plan_id }}
            </button>
          </span>
        </h1>
        <!-- планы дня по порядку: исходный, его пересчёты и тот, по которому ездят сейчас -->
        <nav v-if="openedChain.length" class="plan-chain">
          Планы дня:
          <template v-for="(item, index) in openedChain" :key="item.id">
            <span v-if="index" class="chain-arrow" aria-hidden="true">→</span>
            <strong v-if="item.id === selectedPlanId">№{{ item.id }}</strong>
            <button v-else class="link plan-link" @click="openPlan(item.id)">№{{ item.id }}</button>
            <span class="chain-when">{{ chainWhen(item) }}</span>
          </template>
        </nav>
        <p v-if="openedSummary">
          {{ openedSummary.solver ?? '—' }} · назначено {{ openedSummary.assigned_count }} · не назначено
          {{ openedSummary.unassigned_count }} · исполнителей {{ openedSummary.engineers_used }}<template
            v-if="openedSummary.total_distance_km !== null"
          >
            · {{ openedSummary.total_distance_km.toFixed(1) }} км</template
          >
        </p>
      </template>
    </header>

    <!-- список планов дня: отсюда строят, утверждают, удаляют и открывают план -->
    <template v-if="!planOpened">
      <DayPanel
        :disabled="building"
        :summary="`планов на этот день ${plans.length}`"
        refreshable
        @refresh="loadPlans"
      />

      <section class="plan-toolbar">
        <button class="primary" :disabled="!selectedDay || building" @click="buildDialogOpen = true">
          {{ building ? 'Считаю…' : 'Построить план' }}
        </button>
      </section>

      <!-- расчёт идёт: видно, что именно считается и сколько уже прошло -->
      <PlanRunProgress v-if="building" :run="planRun" @cancel="cancelRun" />

      <ErrorMessage v-if="errorMessage" :message="errorMessage" :details="errorDetails" @close="errorMessage = ''" />
      <ReplanNotice
        v-if="replanSummary?.approved_at"
        :summary="replanSummary"
        :references="references"
        @close="replanPlanId = null"
        @replan="replanTarget = replanSummary"
      />

      <p v-if="loadingDays" class="muted">Загружаю планы…</p>
      <p v-else-if="!plans.length && !building" class="muted">На этот день планов ещё нет — постройте первый.</p>

      <section v-else class="plans-block">
        <h2>Планы на {{ formatDay(selectedDay) }} · {{ plans.length }}</h2>
        <PlansList
          :plans="plans"
          :selected-plan-id="selectedPlanId"
          :busy="building"
          :held-requests="dayCheck?.held_requests ?? []"
          @select="openPlan"
          @remove="removePlan"
          @approve="requestApproval"
          @cancel-approval="cancelApproval"
          @replan-info="replanPlanId = $event"
          @replan="replanTarget = $event"
        />
      </section>
    </template>

    <!-- маршруты одного плана; стрелка возвращает к списку того же дня -->
    <template v-else>
      <section class="plan-day-bar">
        <button class="back-button" :title="`Вернуться к списку планов на ${formatDay(selectedDay)}`" @click="backToPlans">
          <span aria-hidden="true">←</span> Планы на {{ formatDay(selectedDay) }}
        </button>
        <!-- бригады отмечаются в приложении, а диспетчер мог снять заявку: перечитываем план -->
        <IconButton
          icon="refresh"
          label="Обновить план: отметки бригад и снятые заявки"
          :disabled="loadingPlan"
          @click="selectPlan(plan.id)"
        />
      </section>

      <ErrorMessage v-if="errorMessage" :message="errorMessage" :details="errorDetails" @close="errorMessage = ''" />
      <ReplanNotice
        v-if="replanSummary?.approved_at"
        :summary="replanSummary"
        :references="references"
        @close="replanPlanId = null"
        @replan="replanTarget = replanSummary"
      />

      <PlanRunProgress v-if="building" :run="planRun" @cancel="cancelRun" />

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
              Маршруты
            </button>
            <button
              role="tab"
              :aria-selected="viewMode === 'map'"
              :class="{ active: viewMode === 'map' }"
              @click="viewMode = 'map'"
            >
              Карта · маршрутов {{ plan.routes.length }}
            </button>
          </div>

          <!-- режим демонстрации: отмеченные в таблице маршруты приводятся к плану на текущее время -->
          <button
            v-if="syncable"
            class="sync-button"
            :disabled="!syncSelected.length || syncing || building"
            :title="
              syncSelected.length
                ? 'Синхронизировать с планом: отмеченные бригады встанут туда, где они должны быть по плану на текущее системное время; остальные — как есть'
                : 'Синхронизировать с планом: отметьте маршруты галочками в таблице'
            "
            @click="syncChosen"
          >
            <!-- коротко: что именно делает кнопка — в подсказке -->
            {{ syncing ? 'Синхронизирую…' : `По плану${syncSelected.length ? ` (${syncSelected.length})` : ''}` }}
          </button>
          <button
            v-if="openedSummary?.approved_at && !openedSummary?.superseded_at"
            class="primary replan-button"
            :disabled="building"
            title="Пересчитать остаток дня с текущего момента: выполненное и начатое остаётся за бригадами"
            @click="replanTarget = openedSummary"
          >
            Пересчитать
          </button>
        </div>

        <div :class="['plan-view', { 'with-map': viewMode === 'map' }]">
          <div v-if="viewMode === 'map'" class="map-area">
            <PlanMap
              :plan="plan"
              :selected-engineer-id="selectedEngineerId"
              :focused-request-id="focusedRequestId"
              :references="references"
              :approved="Boolean(openedSummary?.approved_at)"
              @select-engineer="selectEngineer"
              @focus-request="focusVisit"
            />
          </div>
          <div class="panel-area">
            <PlanRoutesPanel
              :plan="plan"
              :references="references"
              :selected-engineer-id="selectedEngineerId"
              :beside-map="viewMode === 'map'"
              :approved="Boolean(openedSummary?.approved_at)"
              :focused-request-id="focusedRequestId"
              @visit-status-changed="markVisitStatus"
              @allow-departure="allowDeparture"
              v-model:sync-selected="syncSelected"
              :syncable="syncable"
              @focus-request="focusVisit"
              @select-engineer="viewMode === 'details' ? showRouteOnMap($event) : selectEngineer($event)"
            />
          </div>
        </div>
      </template>
    </template>

    <PlanBuildDialog
      v-if="replanTarget"
      :plan-date="selectedDay"
      :replan-of="replanTarget"
      :routes="replanRoutes"
      :building="building"
      @build="startReplan"
      @close="replanTarget = null"
    />
    <PlanApprovalDialog
      v-if="approvalTarget"
      :summary="approvalTarget"
      :building="building"
      @approve="approveAsIs"
      @decide="startDecisions"
      @close="approvalTarget = null"
    />
    <PlanBuildDialog
      v-if="buildDialogOpen"
      :plan-date="selectedDay"
      :day-check="dayCheck"
      :building="building"
      @build="startBuild"
      @close="buildDialogOpen = false"
    />

    <Transition name="toast">
      <div v-if="noticeMessage" class="toast" role="status">{{ noticeMessage }}</div>
    </Transition>
  </div>
</template>

<style scoped>
/* пересчёт открытого плана — справа в полосе переключателей */
.badge.superseded {
  background: #f1f5f9;
  color: #64748b;
}

.replan-title {
  color: #64748b;
  font-size: 14px;
  font-weight: 400;
}

/* планы дня по порядку: №19 → №22 → №41 (действует) */
.plan-chain {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 6px;
  margin: 4px 0 0;
  color: #64748b;
  font-size: 13px;
}

.plan-chain strong {
  color: #0f172a;
}

.chain-when {
  margin-right: 6px;
  color: #94a3b8;
  font-size: 12px;
}

.plan-link {
  font-size: inherit;
}

/* обе кнопки действий с планом — у правого края, синхронизация перед пересчётом */
.sync-button {
  margin-left: auto;
  order: 1;
}

.sync-button + .replan-button {
  margin-left: 0;
}

.replan-button {
  margin-left: auto;
  order: 1;
}


.plan-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* полоса возврата — того же вида и на том же месте, что полоса дня в списке планов */
.plan-day-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  min-height: 56px;
  padding: 10px 14px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #f8fafc;
  font-size: 13px;
}

/* «← Планы на …» — заметная, но второстепенная кнопка: как ссылка, с рамкой при наведении */
.back-button {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px 4px 6px;
  border-color: transparent;
  background: none;
  color: #2563eb;
  font-weight: 600;
}

.back-button:hover:not(:disabled) {
  border-color: #bfdbfe;
  background: #eff6ff;
}

.badge.approved {
  background: #dcfce7;
  color: #166534;
  font-size: 12px;
  font-weight: 600;
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

.plan-view {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 14px;
  align-items: start;
}

/* карта плана занимает всё место до низа окна: рабочая область — колонка во всю высоту,
   вид карты забирает её остаток. Карта и панель маршрутов справа одной высоты, у панели
   своя прокрутка. Меньше 480 пикселей карта не становится — тогда прокручивается страница. */
.plan-view.with-map {
  flex: 1;
  grid-template-columns: minmax(0, 1fr) 380px;
  grid-template-rows: minmax(0, 1fr);
  align-items: stretch;
  min-height: 480px;
}

.plan-view.with-map .map-area {
  height: auto;
  min-height: 0;
}

.plan-view.with-map .panel-area {
  min-height: 0;
  overflow: auto;
  padding-right: 4px;
}

@media (max-width: 1000px) {
  .plan-view.with-map {
    flex: none;
    grid-template-columns: 1fr;
    grid-template-rows: auto;
  }

  .plan-view.with-map .map-area {
    height: 480px;
  }

  .plan-view.with-map .panel-area {
    overflow: visible;
  }
}
</style>
