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
import { fetchActiveRun } from '../api/systemApi.js'
import { usePlanFocus } from '../composables/usePlanFocus.js'
import { usePlanRun } from '../composables/usePlanRun.js'
import { useSystemTime } from '../composables/useSystemTime.js'
import { usePlans } from '../composables/usePlans.js'
import { formatDay, moscowTimeOf } from '../utils/moscowTime.js'
import { planChain } from '../utils/planChain.js'
import { planWindowOf } from '../utils/planWindow.js'

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

// расчёт идёт на сервере, а не в браузере: ушли со страницы и вернулись — снова показываем
// его ход. Иначе кажется, что расчёт пропал, хотя он считается дальше
const backgroundRun = ref(false)
const runInProgress = computed(() => building.value || backgroundRun.value)

async function attachRunningCalculation() {
  try {
    const active = await fetchActiveRun()
    if (!active) return
    backgroundRun.value = true
    watchRun(active.id)
  } catch {
    // журнал — подсказка, а не работа: без него страница работает как раньше
  }
}

// расчёт, к которому мы подключились, закончился: снимаем полосу и перечитываем планы —
// в списке должен появиться готовый план
watch(planRun, async (value) => {
  if (!backgroundRun.value || !value || value.status === 'running') return
  backgroundRun.value = false
  stopRun()
  await load()
})

// черновик с невлезшими заявками: «Утвердить» просит по каждой решение (перенос или отмена)
// и утверждает план как есть, «Подобрать окна» — второй расчёт с раскрытыми окнами
const approvalTarget = ref(null)
const approvalMode = ref('approve')

function requestApproval(summary) {
  // решать не по кому — утверждаем сразу; иначе спрашиваем по каждой невлезшей.
  // У пересчёта то же самое: он вступит в силу в свой момент, и висящих без решения не оставляем
  if (summary.unassigned_count === 0) {
    approve(summary)
    return
  }
  approvalMode.value = 'approve'
  approvalTarget.value = summary
}

function pickWindows(summary) {
  approvalMode.value = 'windows'
  approvalTarget.value = summary
}

// после подбора окон в дне появился новый расчёт: список нужно перечитать, даже если
// оператор просто закрыл окно, не приняв решений
function closeApproval(result) {
  approvalTarget.value = null
  if (result?.planned) loadPlans()
}

// решать не по кому: утверждаем тот расчёт, который смотрели — у подбора окон это новый
function approveAsIs(planId) {
  const summary = plans.value.find((item) => item.id === planId) ?? approvalTarget.value
  approvalTarget.value = null
  approve(summary)
}

async function startDecisions({ planId, decisions }) {
  // решения принимаются по тому расчёту, который на экране: подбор окон дал новый
  const summary = plans.value.find((item) => item.id === planId) ?? approvalTarget.value
  // «Утвердить»: решения только убирают работу из дня — план утверждается тем же действием
  const approveAfter = approvalMode.value === 'approve'
  approvalTarget.value = null
  const params = { decisions }
  await withRunLog(params, () => decideApproval(summary, params, { approveAfter }))
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
const { demoMode, now } = useSystemTime()
// открыт неутверждённый пересчёт: когда он вступит в силу и сколько осталось на утверждение
const effectWindow = computed(() => planWindowOf(openedSummary.value, now.value))
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
  // пока смотрели план, бригады могли отметиться или отстать: список должен показать «!»
  // сразу, а не после того, как оператор нажмёт «Обновить»
  loadPlans()
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

// участки выбранного маршрута, которые показать на карте: огромный маршрут целиком не разглядеть.
// { engineerId, indexes }; null — маршрут целиком
const chosenLegs = ref(null)

function chooseLegs({ engineerId, indexes }) {
  chosenLegs.value = indexes.length ? { engineerId, indexes } : null
  if (!indexes.length) return
  // участки видно только на карте и только у выбранного маршрута
  selectedEngineerId.value = engineerId
  viewMode.value = 'map'
}

// выбрали другую бригаду или другой план — участки прошлого маршрута уже ни при чём
watch([selectedEngineerId, selectedPlanId], ([engineerId]) => {
  if (chosenLegs.value?.engineerId !== engineerId) chosenLegs.value = null
})

// открытый план и вид переживают перезагрузку страницы: иначе F5 выкидывает к списку планов.
// Читаем до загрузки — загрузка списка сама сбрасывает выбранный план
const OPENED_PLAN_KEY = 'routing.openedPlan'

function storedOpenedPlan() {
  try {
    return JSON.parse(window.localStorage.getItem(OPENED_PLAN_KEY) ?? 'null')
  } catch {
    return null
  }
}

const openedBeforeReload = storedOpenedPlan()

watch([selectedPlanId, viewMode], ([planId, mode]) => {
  try {
    if (planId === null) window.localStorage.removeItem(OPENED_PLAN_KEY)
    else window.localStorage.setItem(OPENED_PLAN_KEY, JSON.stringify({ day: selectedDay.value, planId, mode }))
  } catch {
    // не смогли запомнить — после перезагрузки откроется список планов
  }
})

onMounted(async () => {
  await load()
  attachRunningCalculation()
  const planId = takePlanId()
  const requestId = takePlanRequestId()
  if (planId) {
    await selectPlan(planId)
    if (requestId !== null && plan.value) focusRequest(requestId)
    return
  }
  // тот же день и план ещё есть в списке (его могли удалить или сменить офис)
  const stored = openedBeforeReload
  if (stored?.day === selectedDay.value && plans.value.some((summary) => summary.id === stored.planId)) {
    await selectPlan(stored.planId)
    if (stored.mode === 'map' || stored.mode === 'details') viewMode.value = stored.mode
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
          <!-- на день действует другой план: этот расчёт уже не утвердить -->
          <span
            v-else-if="openedSummary?.outdated"
            class="badge outdated"
            title="На этот день действует другой план — этот расчёт остаётся в истории дня"
          >
            неактуален
          </span>
          <span v-if="openedSummary?.parent_plan_id" class="replan-title">
            пересчёт плана
            <button class="link plan-link" @click="openPlan(openedSummary.parent_plan_id)">
              №{{ openedSummary.parent_plan_id }}
            </button>
            на {{ moscowTimeOf(openedSummary.replanned_at) }}
          </span>
          <!-- пересчёт ещё не утверждён: когда он вступит в силу и сколько осталось -->
          <span
            v-if="effectWindow"
            :class="['badge', 'takes-effect', effectWindow.state]"
            :title="effectWindow.title"
          >
            {{ effectWindow.text }}
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
        <button
          class="primary"
          :disabled="!selectedDay || runInProgress"
          :title="backgroundRun ? 'Расчёт уже идёт — дождитесь его или прервите' : ''"
          @click="buildDialogOpen = true"
        >
          {{ runInProgress ? 'Считаю…' : 'Построить план' }}
        </button>
      </section>

      <!-- расчёт идёт: видно, что именно считается и сколько уже прошло -->
      <PlanRunProgress v-if="runInProgress" :run="planRun" @cancel="cancelRun" />

      <ErrorMessage v-if="errorMessage" :message="errorMessage" :details="errorDetails" @close="errorMessage = ''" />
      <ReplanNotice
        v-if="replanSummary?.approved_at"
        :summary="replanSummary"
        :references="references"
        @close="replanPlanId = null"
      />

      <p v-if="loadingDays" class="muted">Загружаю планы…</p>
      <p v-else-if="!plans.length && !runInProgress" class="muted">
        На этот день планов ещё нет — постройте первый.
      </p>

      <section v-else class="plans-block">
        <h2>Планы на {{ formatDay(selectedDay) }} · {{ plans.length }}</h2>
        <PlansList
          :plans="plans"
          :selected-plan-id="selectedPlanId"
          :busy="runInProgress"
          :held-requests="dayCheck?.held_requests ?? []"
          :attention-plan-id="replanSummary?.approved_at ? replanSummary.id : null"
          :attention-replan-id="replanSummary?.pending_replan_id ?? null"
          @select="openPlan"
          @remove="removePlan"
          @approve="requestApproval"
          @pick-windows="pickWindows"
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
      />

      <PlanRunProgress v-if="runInProgress" :run="planRun" @cancel="cancelRun" />

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
            :class="['primary', 'replan-button', {
              'attention-pulse':
                replanSummary?.approved_at &&
                replanSummary.id === openedSummary.id &&
                !replanSummary.pending_replan_id,
            }]"
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
              :chosen-legs="chosenLegs"
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
              :chosen-legs="chosenLegs"
              :pending-replan-id="openedSummary?.pending_replan_id ?? null"
              @choose-legs="chooseLegs"
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
      :mode="approvalMode"
      @approve="approveAsIs"
      @decide="startDecisions"
      @close="closeApproval"
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

/* неутверждённый пересчёт: когда он вступит в силу и сколько осталось на утверждение */
.badge.takes-effect {
  background: #eef2ff;
  color: #3730a3;
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

/* устаревший черновик: не ошибка, просто история дня */
.badge.outdated {
  background: #f1f5f9;
  color: #64748b;
}
</style>
