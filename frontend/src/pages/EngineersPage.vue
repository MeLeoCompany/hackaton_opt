<script setup>
import { computed, onMounted, ref } from 'vue'

import DayPanel from '../components/DayPanel.vue'
import EngineerDetailsCard from '../components/EngineerDetailsCard.vue'
import EngineersFilters from '../components/EngineersFilters.vue'
import EngineersMap from '../components/EngineersMap.vue'
import EngineersTable from '../components/EngineersTable.vue'
import { useEngineersTable } from '../composables/useEngineersTable.js'
import { useEngineersView } from '../composables/useEngineersView.js'

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

    <DayPanel :summary="`исполнителей со сменой в этот день ${engineers.length}`" />

    <EngineersFilters
      :filters="filters"
      :references="references"
      :active-count="activeFilterCount"
      @reset="resetFilters"
    />

    <div v-if="errorMessage" class="message error">
      <strong>{{ errorMessage }}</strong>
      <ul v-if="errorDetails.length">
        <li v-for="(detail, index) in errorDetails" :key="index">{{ detail }}</li>
      </ul>
    </div>

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
          @sort="toggleSort"
          @select="selectEngineer"
          @edit="startEdit"
          @cancel="cancelEdit"
          @save="saveForm"
          @remove="remove"
        />
      </div>

      <div v-else class="map-view">
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
