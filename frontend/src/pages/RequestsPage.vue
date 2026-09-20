<script setup>
import { computed, onMounted, ref, watch } from 'vue'

import ErrorMessage from '../components/ErrorMessage.vue'
import DayPanel from '../components/DayPanel.vue'
import DayTransferDialog from '../components/DayTransferDialog.vue'
import RequestCopyDialog from '../components/RequestCopyDialog.vue'
import RequestDetailsCard from '../components/RequestDetailsCard.vue'
import RequestHistoryDialog from '../components/RequestHistoryDialog.vue'
import RequestsFilters from '../components/RequestsFilters.vue'
import RequestsMap from '../components/RequestsMap.vue'
import RequestsPagination from '../components/RequestsPagination.vue'
import RequestsTable from '../components/RequestsTable.vue'
import { usePlanFocus } from '../composables/usePlanFocus.js'
import { useDayPlanWarning } from '../composables/useDayPlanWarning.js'
import { useSelectedDay } from '../composables/useSelectedDay.js'
import { useRequestsTable } from '../composables/useRequestsTable.js'
import { REQUEST_COLUMNS, useRequestsView } from '../composables/useRequestsView.js'
import { movedAway } from '../utils/requestMarks.js'

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
  duplicate,
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

// сколько заявок пойдёт в расчёт этого дня: статусы Новая и В плане, кроме перенесённых отсюда
const activeTotal = computed(
  () => requests.value.filter((request) => request.is_active && !movedAway(request, selectedDay.value)).length,
)

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

const { selectedDay, refreshDaysWithRequests } = useSelectedDay()

// утверждённый план дня: если с ним что-то разошлось, предупреждаем прямо здесь
const { planSummary, pendingReplan, needsReplan, load: loadDayPlan } = useDayPlanWarning()

// обновить всё, что могло измениться: заявки, план дня и дни с заявками
async function refreshDay() {
  await Promise.all([load(), loadDayPlan(), refreshDaysWithRequests()])
}

// файл, который переносят в выбранный день: ждёт ответа про отменённые заявки
const transferFile = ref(null)

async function transferDay(cancelled) {
  const file = transferFile.value
  transferFile.value = null
  await importDay(file, cancelled)
}

// копия отменённой: сначала спрашиваем день копии — работу могли перенести на другой день
const copySource = ref(null)

// копия отменённой — сразу строкой правки; фильтры могут её скрыть, тогда снимаем их
async function duplicateAndShow(request, planDate) {
  copySource.value = null
  const copyId = await duplicate(request, planDate === selectedDay.value ? null : planDate)
  if (copyId === null) return
  if (!filteredRequests.value.some((item) => item.id === copyId)) resetFilters()
  selectRequest(copyId)
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

// Смена дня или заявок меняет причины пересчёта; перечитываем сводку плана.
watch([selectedDay, requests], loadDayPlan)

onMounted(async () => {
  await Promise.all([load(), loadDayPlan()])
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
      refreshable
      @refresh="refreshDay"
      @export-day="exportDay"
      @import-day="transferFile = $event"
    />


    <!-- с утверждённым планом дня что-то разошлось: оператор видит это, не заходя в планы -->
    <p v-if="pendingReplan" class="replan-warning">
      <span>⚠ Пересчёт №{{ pendingReplan.id }} посчитан — утвердите его, бригады ждут маршрут</span>
      <button type="button" class="link" @click="openPlan(pendingReplan.id)">
        Открыть пересчёт №{{ pendingReplan.id }} →
      </button>
    </p>
    <p v-else-if="needsReplan" class="replan-warning">
      <span>⚠ Рекомендуется пересчитать план</span>
      <button type="button" class="link" @click="openPlan(planSummary.id)">Открыть план №{{ planSummary.id }} →</button>
    </p>

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
          :plan-date="selectedDay"
          @sort="toggleSort"
          @select="selectRequest"
          @change-status="changeStatus"
          @history="historyRequestId = $event.id"
          @open-plan="openPlan($event.approved_plan_id, $event.id)"
          @edit="startEdit"
          @cancel="cancelEdit"
          @save="saveForm"
          @remove="remove"
          @duplicate="copySource = $event"
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

    <RequestCopyDialog
      v-if="copySource"
      :request="copySource"
      @copy="duplicateAndShow(copySource, $event)"
      @close="copySource = null"
    />

    <!-- перенос слепка дня: отдельно спрашиваем, что делать с отменёнными из файла -->
    <DayTransferDialog
      v-if="transferFile"
      :file-name="transferFile.name"
      :day="selectedDay"
      :existing="requests.length"
      @transfer="transferDay"
      @close="transferFile = null"
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
/* предупреждение про утверждённый план дня: жёлтая полоса, заметная, но не красная ошибка */
.replan-warning {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 12px;
  margin: 0;
  padding: 8px 12px;
  border: 1px solid #fcd34d;
  border-radius: 8px;
  background: #fffbeb;
  color: #92400e;
  font-size: 13px;
}

.replan-warning .link {
  color: #b45309;
  font-weight: 600;
}
</style>
