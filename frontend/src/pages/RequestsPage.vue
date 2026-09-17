<script setup>
import { computed, onMounted, ref } from 'vue'

import DayPanel from '../components/DayPanel.vue'
import RequestDetailsCard from '../components/RequestDetailsCard.vue'
import RequestsFilters from '../components/RequestsFilters.vue'
import RequestsMap from '../components/RequestsMap.vue'
import RequestsPagination from '../components/RequestsPagination.vue'
import RequestsTable from '../components/RequestsTable.vue'
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
  setActive,
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

// что показываем под фильтрами: 'table' или 'map'
const viewMode = ref('table')

// карточка справа от карты занимает ровно две последние колонки таблицы: её левый край
// совпадает с линией колонки в шапке фильтров, а карта заканчивается перед ней
// +1 — правая рамка блока с таблицей: колонки начинаются внутри неё
const DETAILS_WIDTH = REQUEST_COLUMNS.slice(-2).reduce((sum, column) => sum + parseInt(column.width, 10), 0) + 1

const selectedRequest = computed(
  () => filteredRequests.value.find((request) => request.id === selectedId.value) ?? null,
)

const activeTotal = computed(() => requests.value.filter((request) => request.is_active).length)
const activeShown = computed(() => filteredRequests.value.filter((request) => request.is_active).length)
const inactiveShown = computed(() => filteredRequests.value.length - activeShown.value)

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

function toggleActive(request) {
  setActive([request.id], !request.is_active)
}

// включить или выключить разом все заявки, которые сейчас показаны по фильтрам
function setActiveForShown(isActive) {
  const targetIds = filteredRequests.value
    .filter((request) => request.is_active !== isActive)
    .map((request) => request.id)
  if (targetIds.length === 0) return

  const action = isActive ? 'Включить' : 'Выключить'
  if (targetIds.length > 1 && !window.confirm(`${action} показанные заявки: ${targetIds.length} шт.?`)) return
  setActive(targetIds, isActive)
}

onMounted(load)
</script>

<template>
  <div class="workspace">
    <header class="workspace-title">
      <h1>Заявки</h1>
      <p>
        Всего {{ requests.length }} · активных {{ activeTotal }}<template v-if="activeFilterCount">
          · по фильтрам {{ filteredRequests.length }}</template
        >
        · время московское
      </p>
    </header>

    <DayPanel
      :summary="`заявок на этот день ${requests.length}, активных ${activeTotal}`"
      transfer="заявки"
      :disabled="saving"
      @export-day="exportDay"
      @import-day="importDay"
    />


    <div v-if="errorMessage" class="message error">
      <strong>{{ errorMessage }}</strong>
      <ul v-if="errorDetails.length">
        <li v-for="(detail, index) in errorDetails" :key="index">{{ detail }}</li>
      </ul>
    </div>

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

        <div class="list-bar-group">
          <span class="list-bar-note">Активных {{ activeShown }} из {{ filteredRequests.length }} показанных</span>
          <button :disabled="editingId !== null || activeShown === 0" @click="setActiveForShown(false)">
            Выключить показанные
          </button>
          <button :disabled="editingId !== null || inactiveShown === 0" @click="setActiveForShown(true)">
            Включить показанные
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
          @toggle-active="toggleActive"
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

      <div v-else class="map-view" :style="{ '--details-width': `${DETAILS_WIDTH}px` }">
        <RequestsFilters
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
          @toggle-active="toggleActive(selectedRequest)"
          @close="selectedId = null"
        />
      </div>
    </template>

    <Transition name="toast">
      <div v-if="noticeMessage" class="toast" role="status">{{ noticeMessage }}</div>
    </Transition>
  </div>
</template>
