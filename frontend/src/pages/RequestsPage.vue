<script setup>
import { computed, onMounted, ref } from 'vue'

import ErrorMessage from '../components/ErrorMessage.vue'
import DayPanel from '../components/DayPanel.vue'
import RequestDetailsCard from '../components/RequestDetailsCard.vue'
import RequestHistoryDialog from '../components/RequestHistoryDialog.vue'
import RequestsFilters from '../components/RequestsFilters.vue'
import RequestsMap from '../components/RequestsMap.vue'
import RequestsPagination from '../components/RequestsPagination.vue'
import RequestsTable from '../components/RequestsTable.vue'
import { usePlanFocus } from '../composables/usePlanFocus.js'
import { useRequestsTable } from '../composables/useRequestsTable.js'
import { REQUEST_COLUMNS, useRequestsView } from '../composables/useRequestsView.js'

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

// сколько заявок пойдёт в расчёт плана: статусы Новая и В плане
const activeTotal = computed(() => requests.value.filter((request) => request.is_active).length)

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

// копия отменённой — сразу строкой правки; фильтры могут её скрыть, тогда снимаем их
async function duplicateAndShow(request) {
  const copyId = await duplicate(request)
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

onMounted(async () => {
  await load()
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
          @duplicate="duplicateAndShow"
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
