<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'

import ErrorMessage from '../components/ErrorMessage.vue'
import DayPanel from '../components/DayPanel.vue'
import EngineerDetailsCard from '../components/EngineerDetailsCard.vue'
import EngineersFilters from '../components/EngineersFilters.vue'
import EngineersMap from '../components/EngineersMap.vue'
import EngineersTable from '../components/EngineersTable.vue'
import EngineersBulkEditDialog from '../components/EngineersBulkEditDialog.vue'
import BulkActionsBar from '../components/BulkActionsBar.vue'
import { deleteEngineers, updateEngineers } from '../api/engineersApi.js'
import { useBulkSelection } from '../composables/useBulkSelection.js'
import { useSelectedDay } from '../composables/useSelectedDay.js'
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
  showNotice,
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
  lastCreatedId,
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
} = useEngineersView(engineers, references, lastCreatedId)

// добавили исполнителя — он первой строкой и выделен: видно, что появилось
watch(lastCreatedId, (engineerId) => {
  if (engineerId !== null) selectedId.value = engineerId
})

// что показываем под фильтрами: 'table' или 'map'
const viewMode = ref('table')
// карта короче экрана, а над ней бывают плашки предупреждений: при переходе на карту
// прокручиваем страницу к ней, иначе отмеченные точки остаются ниже края экрана
const mapArea = ref(null)
const bulkBar = ref(null)

watch(viewMode, async (mode) => {
  if (mode !== 'map') return
  await nextTick()
  const target = bulkBar.value?.$el ?? mapArea.value
  target?.scrollIntoView({ block: 'start', behavior: 'smooth' })
})

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

// «Сбросить» в строке фильтров снимает всё, чем сужен список: и фильтры, и отметки
function resetEverything() {
  resetFilters()
  selection.clear()
}

// галочки в таблице: отмеченные смены меняют и удаляют группой
const selection = useBulkSelection(() => sortedEngineers.value)
const bulkEditOpen = ref(false)
const bulkSaving = ref(false)
const { selectedDay } = useSelectedDay()

// смены перечитали — отметки на исчезнувших снимаем сами
watch(engineers, () => selection.keepOnly(engineers.value.map((engineer) => engineer.id)))

function plural(count, one, few, many) {
  const tens = count % 100
  const units = count % 10
  if (tens >= 11 && tens <= 14) return `${count} ${many}`
  if (units === 1) return `${count} ${one}`
  if (units >= 2 && units <= 4) return `${count} ${few}`
  return `${count} ${many}`
}

const selectedTitle = computed(() => plural(selection.count.value, 'смена', 'смены', 'смен'))

// общий обвес группового действия: занятость и разбор ошибки сервера
async function runBulk(action) {
  bulkSaving.value = true
  errorMessage.value = ''
  errorDetails.value = []
  try {
    return await action()
  } catch (error) {
    errorMessage.value = error.message
    errorDetails.value = error.details ?? []
    return null
  } finally {
    bulkSaving.value = false
  }
}

// групповая правка: сервер меняет либо все отмеченные смены, либо ни одной
async function applyBulkEdit(fields) {
  const report = await runBulk(() => updateEngineers(selection.selectedIds.value, fields))
  if (report === null) return
  bulkEditOpen.value = false
  selection.clear()
  await load()
  showNotice(`Изменено: ${plural(report.updated, 'смена', 'смены', 'смен')}`)
}

// групповое удаление: что можно — удаляем, про остальное показываем причины
async function removeSelected() {
  const ids = selection.selectedIds.value
  if (!window.confirm(`Удалить ${plural(ids.length, 'смену', 'смены', 'смен')}?`)) return
  const report = await runBulk(() => deleteEngineers(ids))
  if (report === null) return
  selection.clear()
  await load()
  if (report.problems.length) {
    errorMessage.value = `Удалено: ${report.deleted}. Не удалось удалить: ${report.problems.length}`
    errorDetails.value = report.problems.map((problem) => problem.reason)
    return
  }
  showNotice(`Удалено: ${plural(report.deleted, 'смена', 'смены', 'смен')}`)
}

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

      <!-- отмечены строки: действия доступны и в таблице, и на карте -->
      <BulkActionsBar
        ref="bulkBar"
        v-if="selection.count.value"
        :count="selection.count.value"
        :title="selectedTitle"
        :busy="bulkSaving || saving"
        @edit="bulkEditOpen = true"
        @delete="removeSelected"
      />

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
          :selected-ids="selection.selectedIds.value"
          :all-selected="selection.allVisibleSelected.value"
          :some-selected="selection.someVisibleSelected.value"
          @toggle-row="selection.toggleRow"
          @toggle-all="selection.toggleVisible"
          @sort="toggleSort"
          @select="selectEngineer"
          @edit="startEdit"
          @cancel="cancelEdit"
          @save="saveForm"
          @remove="remove"
          @reset-filters="resetEverything"
          @show-on-map="showOnMap"
        />
      </div>

      <div v-else ref="mapArea" class="map-view" :style="{ '--details-width': detailsWidth }">
        <EngineersFilters
          @widths="filterWidths = $event"
          :filters="filters"
          :references="references"
          :active-count="activeFilterCount"
          :checked-count="selection.count.value"
          @reset="resetEverything"
        />

        <div class="map-area">
          <EngineersMap
            :engineers="filteredEngineers"
            :references="references"
            :selected-id="selectedId"
            :checked-ids="selection.selectedIds.value"
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

    <EngineersBulkEditDialog
      v-if="bulkEditOpen"
      :count="selection.count.value"
      :references="references"
      :saving="bulkSaving"
      :plan-date="selectedDay"
      @apply="applyBulkEdit"
      @close="bulkEditOpen = false"
    />

    <Transition name="toast">
      <div v-if="noticeMessage" class="toast" role="status">{{ noticeMessage }}</div>
    </Transition>
  </div>
</template>
