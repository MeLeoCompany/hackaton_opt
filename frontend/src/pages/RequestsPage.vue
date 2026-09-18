<script setup>
import { computed, onMounted, ref, watch } from 'vue'

import DaySyncDialog from '../components/DaySyncDialog.vue'
import ErrorMessage from '../components/ErrorMessage.vue'
import IconButton from '../components/IconButton.vue'
import DayPanel from '../components/DayPanel.vue'
import RequestDetailsCard from '../components/RequestDetailsCard.vue'
import RequestHistoryDialog from '../components/RequestHistoryDialog.vue'
import RequestsFilters from '../components/RequestsFilters.vue'
import RequestsMap from '../components/RequestsMap.vue'
import RequestsPagination from '../components/RequestsPagination.vue'
import RequestsTable from '../components/RequestsTable.vue'
import { getDaySync } from '../api/plansApi.js'
import { usePlanFocus } from '../composables/usePlanFocus.js'
import { useRequestsTable } from '../composables/useRequestsTable.js'
import { REQUEST_COLUMNS, useRequestsView } from '../composables/useRequestsView.js'
import { useSelectedDay } from '../composables/useSelectedDay.js'
import { formatSyncMoment, syncSummary } from '../utils/daySync.js'
import { statusCode } from '../utils/requestStatuses.js'

// данные и их изменение
const {
  requests,
  references,
  applyWorkTypeNorms,
  exportDay,
  importDay,
  loading,
  saving,
  errorMessage,
  errorDetails,
  noticeMessage,
  editingId,
  form,
  load,
  startCreate,
  startEdit,
  cancelEdit,
  saveForm,
  remove,
  setStatus,
  showNotice,
} = useRequestsTable()

// что из данных видно: фильтры, сортировка, страница, выбранная заявка
const {
  filters,
  activeFilterCount,
  filteredRequests,
  resetFilters,
  sortKey,
  sortDirection,
  toggleSort,
  page,
  pageSize,
  pageCount,
  currentPage,
  pageRequests,
  selectedId,
  selectRequest,
} = useRequestsView(requests, references)

// пришли из маршрута плана — показываем ту самую заявку; обратно — «Открыть в плане»
const { takeRequestId, openPlan } = usePlanFocus()

// что показываем под фильтрами: 'table' или 'map'
const viewMode = ref('table')

// карточка справа от карты занимает ровно три последние колонки таблицы (приоритет,
// транспорт, кнопки) — двух уже мало под её кнопки. Её левый край
// совпадает с линией колонки в шапке фильтров, а карта заканчивается перед ней
// ширины колонок шапки фильтров над картой — приходят от неё самой
const filterWidths = ref({})
const detailsWidth = computed(() => {
  const total = REQUEST_COLUMNS.slice(-3).reduce((sum, column) => sum + (filterWidths.value[column.key] ?? 0), 0)
  // +1 — правая рамка блока с таблицей: колонки начинаются внутри неё
  return total ? `${total + 1}px` : undefined
})

const selectedRequest = computed(
  () => filteredRequests.value.find((request) => request.id === selectedId.value) ?? null,
)

// сколько заявок пойдёт в расчёт плана: статусы Новая и В плане
const activeTotal = computed(() => requests.value.filter((request) => request.is_active).length)

// подсказка к отметке синхронизации: когда и кто её сделал
const syncTitle = computed(() => {
  if (!daySync.value?.synced_at) return ''
  const who = daySync.value.user_name ? `, ${daySync.value.user_name}` : ''
  return `Синхронизацию выполнили ${formatSyncMoment(daySync.value.synced_at, selectedDay.value)}${who}`
})

// заявка, чья история открыта в окне
const historyRequestId = ref(null)

function addRequest() {
  viewMode.value = 'table'
  startCreate()
}

function showInTable(requestId) {
  selectRequest(requestId)
  viewMode.value = 'table'
}

// двойной клик по строке — та же заявка на карте
function showOnMap(requestId) {
  selectRequest(requestId)
  viewMode.value = 'map'
}

function changeStatus(request, statusId) {
  setStatus([request.id], statusId)
}

// заявка из плана может быть скрыта фильтрами прошлой работы — тогда фильтры снимаем,
// иначе выделение тут же слетит и диспетчер решит, что заявки нет
function focusRequest(requestId) {
  if (!requests.value.some((request) => request.id === requestId)) {
    showNotice(`Заявка №${requestId} в этом дне не найдена`)
    return
  }
  if (!filteredRequests.value.some((request) => request.id === requestId)) resetFilters()
  viewMode.value = 'table'
  selectRequest(requestId)
}

// ---- синхронизация дня с утверждённым планом ----

const { selectedDay } = useSelectedDay()
// до какого времени день синхронизирован: { synced_to, synced_at, user_name }
const daySync = ref(null)
// открытое окно синхронизации: 'now' — на текущее время, 'custom' — на заданное; null — закрыто
const syncMode = ref(null)

async function loadDaySync() {
  const day = selectedDay.value
  try {
    const state = await getDaySync(day)
    if (day === selectedDay.value) daySync.value = state
  } catch {
    // без отметки о синхронизации страница работает, кнопки тоже
    daySync.value = null
  }
}

async function onSynced(report) {
  syncMode.value = null
  await Promise.all([load(), loadDaySync()])
  showNotice(
    `Синхронизировано на ${formatSyncMoment(report.sync_time, report.plan_date)}: ` +
      syncSummary(report.transitions, (statusId) => statusCode(references.value, statusId)),
  )
}

watch(selectedDay, loadDaySync)

onMounted(async () => {
  await Promise.all([load(), loadDaySync()])
  const requestId = takeRequestId()
  if (requestId !== null) focusRequest(requestId)
})
</script>

<template>
  <div class="workspace">
    <header class="workspace-title">
      <h1>Заявки</h1>
      <p>
        Всего {{ requests.length }} · к планированию {{ activeTotal }}<template v-if="activeFilterCount">
          · по фильтрам {{ filteredRequests.length }}</template
        >
        · время московское
      </p>
    </header>

    <DayPanel
      :summary="`заявок на этот день ${requests.length}, к планированию ${activeTotal}`"
      transfer="заявки"
      :disabled="saving"
      @export-day="exportDay"
      @import-day="importDay"
    />


    <ErrorMessage v-if="errorMessage" :message="errorMessage" :details="errorDetails" @close="errorMessage = ''" />

    <p v-if="loading" class="muted">Загружаю заявки…</p>

    <template v-else>
      <div class="list-bar">
        <button class="primary" :disabled="editingId !== null" @click="addRequest">+ Добавить заявку</button>

        <div class="view-switch" role="tablist">
          <button
            role="tab"
            :aria-selected="viewMode === 'table'"
            :class="{ active: viewMode === 'table' }"
            @click="viewMode = 'table'"
          >
            Таблица
          </button>
          <button
            role="tab"
            :aria-selected="viewMode === 'map'"
            :class="{ active: viewMode === 'map' }"
            :disabled="editingId !== null"
            :title="editingId !== null ? 'Сначала сохраните или отмените правку заявки' : ''"
            @click="viewMode = 'map'"
          >
            Карта · {{ filteredRequests.length }}
          </button>
        </div>

        <!-- синхронизация дня с утверждённым планом: на текущее время или на заданное.
             Значки справа, под выгрузкой и загрузкой дня — тем же блоком того же размера -->
        <span v-if="daySync?.synced_to" class="list-bar-note sync-note" :title="syncTitle">
          Синхронизировано на {{ formatSyncMoment(daySync.synced_to, selectedDay) }}
        </span>
        <div :class="['sync-buttons', { 'after-note': daySync?.synced_to }]">
          <IconButton
            icon="sync"
            class="sync-now"
            label="Синхронизировать с планом на текущее время"
            :disabled="editingId !== null"
            @click="syncMode = 'now'"
          />
          <IconButton
            icon="clock"
            class="sync-at"
            label="Синхронизировать с планом на заданное время"
            :disabled="editingId !== null"
            @click="syncMode = 'custom'"
          />
        </div>
      </div>

      <div v-if="viewMode === 'table'" class="table-view">
        <RequestsTable
          :requests="pageRequests"
          :references="references"
          :editing-id="editingId"
          :form="form"
          :saving="saving"
          :sort-key="sortKey"
          :sort-direction="sortDirection"
          :selected-id="selectedId"
          :empty-text="requests.length ? 'По фильтрам ничего не найдено' : 'Заявок нет'"
          :filters="filters"
          :active-filter-count="activeFilterCount"
          @sort="toggleSort"
          @select="selectRequest"
          @change-status="changeStatus"
          @history="historyRequestId = $event.id"
          @open-plan="openPlan($event.approved_plan_id, $event.id)"
          @edit="startEdit"
          @cancel="cancelEdit"
          @save="saveForm"
          @remove="remove"
          @work-type-picked="applyWorkTypeNorms"
          @reset-filters="resetFilters"
          @show-on-map="showOnMap"
        />
        <RequestsPagination
          v-model:page-size="pageSize"
          :page="currentPage"
          :page-count="pageCount"
          :total="filteredRequests.length"
          @update:page="page = $event"
        />
      </div>

      <div v-else class="map-view" :style="{ '--details-width': detailsWidth }">
        <RequestsFilters
          @widths="filterWidths = $event"
          :filters="filters"
          :references="references"
          :active-count="activeFilterCount"
          @reset="resetFilters"
        />

        <div class="map-area">
          <RequestsMap
            :requests="filteredRequests"
            :references="references"
            :selected-id="selectedId"
            @select="selectRequest"
          />
        </div>
        <RequestDetailsCard
          :request="selectedRequest"
          :references="references"
          @show-in-table="showInTable(selectedRequest.id)"
          @change-status="changeStatus(selectedRequest, $event)"
          @history="historyRequestId = selectedRequest.id"
          @open-plan="openPlan(selectedRequest.approved_plan_id, selectedRequest.id)"
          @close="selectedId = null"
        />
      </div>
    </template>

    <DaySyncDialog
      v-if="syncMode"
      :plan-date="selectedDay"
      :mode="syncMode"
      :references="references"
      :last-synced-to="daySync?.synced_to ?? null"
      @close="syncMode = null"
      @done="onSynced"
    />

    <RequestHistoryDialog
      v-if="historyRequestId !== null"
      :request-id="historyRequestId"
      :references="references"
      @close="historyRequestId = null"
    />

    <Transition name="toast">
      <div v-if="noticeMessage" class="toast" role="status">{{ noticeMessage }}</div>
    </Transition>
  </div>
</template>

<style scoped>
/* как блок выгрузки и загрузки в полосе дня над ним: у правого края, та же ширина, те же
   кнопки — значки стоят ровно под теми */
.sync-note {
  margin-left: auto;
  white-space: nowrap;
}

.sync-buttons {
  display: flex;
  flex-shrink: 0; /* на узком экране (раскрыто меню) полоса не сжимает значки */
  align-items: center;
  gap: 6px;
  width: 125px;
  margin-left: auto;
  /* у полосы дня внутренний отступ справа — отступаем так же, чтобы значки стояли под теми */
  margin-right: 7px;
  padding-left: 6px;
  border-left: 1px solid #e2e8f0;
}

.sync-buttons.after-note {
  margin-left: 0;
}

.sync-buttons :deep(.icon-button) {
  flex: 1;
  width: auto;
}
</style>
