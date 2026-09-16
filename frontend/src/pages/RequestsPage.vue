<script setup>
import { computed, onMounted, ref } from 'vue'

import RequestDetailsCard from '../components/RequestDetailsCard.vue'
import RequestsCsvImport from '../components/RequestsCsvImport.vue'
import RequestsFilters from '../components/RequestsFilters.vue'
import RequestsMap from '../components/RequestsMap.vue'
import RequestsPagination from '../components/RequestsPagination.vue'
import RequestsTable from '../components/RequestsTable.vue'
import { useRequestsTable } from '../composables/useRequestsTable.js'
import { useRequestsView } from '../composables/useRequestsView.js'

// данные и их изменение
const {
  requests,
  references,
  applyWorkTypeNorms,
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
  importCsv,
  downloadTemplate,
} = useRequestsTable()

// что из данных видно: фильтры, сортировка, страница, выбранная заявка
const {
  filters,
  availableDays,
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

    <RequestsCsvImport :busy="saving" @import="importCsv" @download-template="downloadTemplate" />

    <RequestsFilters
      :filters="filters"
      :references="references"
      :available-days="availableDays"
      :active-count="activeFilterCount"
      @reset="resetFilters"
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
          @sort="toggleSort"
          @select="selectRequest"
          @toggle-active="toggleActive"
          @edit="startEdit"
          @cancel="cancelEdit"
          @save="saveForm"
          @remove="remove"
          @work-type-picked="applyWorkTypeNorms"
        />
        <RequestsPagination
          v-model:page-size="pageSize"
          :page="currentPage"
          :page-count="pageCount"
          :total="filteredRequests.length"
          @update:page="page = $event"
        />
      </div>

      <div v-else class="map-view">
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
