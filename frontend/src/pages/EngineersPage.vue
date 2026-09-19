<script setup>
import { computed, onMounted, ref } from 'vue'

import ErrorMessage from '../components/ErrorMessage.vue'
import DayPanel from '../components/DayPanel.vue'
import EngineerDetailsCard from '../components/EngineerDetailsCard.vue'
import EngineersFilters from '../components/EngineersFilters.vue'
import EngineersMap from '../components/EngineersMap.vue'
import EngineersTable from '../components/EngineersTable.vue'
import { useEngineersTable } from '../composables/useEngineersTable.js'
import { ENGINEER_COLUMNS, useEngineersView } from '../composables/useEngineersView.js'

// данные и их изменение
const {
  engineers,
  references,
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
  exportDay,
  importDay,
} = useEngineersTable()

// что из данных видно: фильтры, сортировка, выбранный исполнитель
const {
  filters,
  activeFilterCount,
  filteredEngineers,
  sortedEngineers,
  resetFilters,
  sortKey,
  sortDirection,
  toggleSort,
  selectedId,
} = useEngineersView(engineers, references)

// что показываем под фильтрами: 'table' или 'map'
const viewMode = ref('table')

// карточка справа от карты занимает ровно три последние колонки таблицы (смена, старт,
// действия): её левый край совпадает с линией колонки в шапке фильтров, а карта
// заканчивается перед ней. Двух узких колонок старта и действий карточке мало.
// ширины колонок шапки фильтров над картой — приходят от неё самой
const filterWidths = ref({})
const detailsWidth = computed(() => {
  const total = ENGINEER_COLUMNS.slice(-3).reduce((sum, column) => sum + (filterWidths.value[column.key] ?? 0), 0)
  // +1 — правая рамка блока с таблицей: колонки начинаются внутри неё
  return total ? `${total + 1}px` : undefined
})

const selectedEngineer = computed(
  () => filteredEngineers.value.find((engineer) => engineer.id === selectedId.value) ?? null,
)

function addEngineer() {
  viewMode.value = 'table'
  startCreate()
}

function selectEngineer(engineerId) {
  selectedId.value = engineerId
}

function showInTable() {
  viewMode.value = 'table'
}

// двойной клик по строке — тот же исполнитель на карте
function showOnMap(engineerId) {
  selectEngineer(engineerId)
  viewMode.value = 'map'
}

onMounted(load)
</script>

<template>
  <div class="workspace">
    <header class="workspace-title">
      <h1>Исполнители</h1>
      <p>
        Всего {{ engineers.length }}<template v-if="activeFilterCount">
          · по фильтрам {{ filteredEngineers.length }}</template
        >
        · время смен московское
      </p>
    </header>

    <DayPanel
      :summary="`исполнителей со сменой в этот день ${engineers.length}`"
      transfer="смены"
      :disabled="saving"
      @export-day="exportDay"
      @import-day="importDay"
    />

    <ErrorMessage v-if="errorMessage" :message="errorMessage" :details="errorDetails" @close="errorMessage = ''" />

    <p v-if="loading" class="muted">Загружаю исполнителей…</p>

    <template v-else>
      <div class="list-bar">
        <button class="primary" :disabled="editingId !== null" @click="addEngineer">+ Добавить исполнителя</button>

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
            :title="editingId !== null ? 'Сначала сохраните или отмените правку исполнителя' : ''"
            @click="viewMode = 'map'"
          >
            Карта · {{ filteredEngineers.length }}
          </button>
        </div>
      </div>

      <div v-if="viewMode === 'table'" class="table-view">
        <EngineersTable
          :engineers="sortedEngineers"
          :references="references"
          :editing-id="editingId"
          :form="form"
          :saving="saving"
          :sort-key="sortKey"
          :sort-direction="sortDirection"
          :selected-id="selectedId"
          :empty-text="engineers.length ? 'По фильтрам никого не найдено' : 'Исполнителей нет'"
          :filters="filters"
          :active-filter-count="activeFilterCount"
          @sort="toggleSort"
          @select="selectEngineer"
          @edit="startEdit"
          @cancel="cancelEdit"
          @save="saveForm"
          @remove="remove"
          @reset-filters="resetFilters"
          @show-on-map="showOnMap"
        />
      </div>

      <div v-else class="map-view" :style="{ '--details-width': detailsWidth }">
        <EngineersFilters
          @widths="filterWidths = $event"
          :filters="filters"
          :references="references"
          :active-count="activeFilterCount"
          @reset="resetFilters"
        />

        <div class="map-area">
          <EngineersMap
            :engineers="filteredEngineers"
            :references="references"
            :selected-id="selectedId"
            @select="selectEngineer"
          />
        </div>
        <EngineerDetailsCard
          :engineer="selectedEngineer"
          :references="references"
          @show-in-table="showInTable"
          @close="selectedId = null"
        />
      </div>
    </template>

    <Transition name="toast">
      <div v-if="noticeMessage" class="toast" role="status">{{ noticeMessage }}</div>
    </Transition>
  </div>
</template>
