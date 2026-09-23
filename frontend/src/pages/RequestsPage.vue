<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'

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
import RequestsBulkEditDialog from '../components/RequestsBulkEditDialog.vue'
import BulkActionsBar from '../components/BulkActionsBar.vue'
import { deleteRequests, updateRequests } from '../api/requestsApi.js'
import { useBulkSelection } from '../composables/useBulkSelection.js'
import { usePlanFocus } from '../composables/usePlanFocus.js'
import { useDayPlanWarning } from '../composables/useDayPlanWarning.js'
import { useSelectedDay } from '../composables/useSelectedDay.js'
import { useSystemTime } from '../composables/useSystemTime.js'
import { useRequestsTable } from '../composables/useRequestsTable.js'
import { REQUEST_COLUMNS, useRequestsView } from '../composables/useRequestsView.js'
import { formatDay } from '../utils/moscowTime.js'
import { movedAway, OVERDUE_FILTER } from '../utils/requestMarks.js'

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
  lastCreatedId,
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
} = useRequestsView(requests, references, lastCreatedId)

// добавили заявку — она первой строкой на первой странице и выделена: видно, что появилось
watch(lastCreatedId, (requestId) => {
  if (requestId === null) return
  page.value = 1
  selectedId.value = requestId
})

// «Сбросить» в строке фильтров снимает всё, чем сужен список: и фильтры, и отметки
function resetEverything() {
  resetFilters()
  selection.clear()
}

// галочки в таблице: отмеченные заявки меняют и удаляют группой
const selection = useBulkSelection(() => pageRequests.value)
const bulkEditOpen = ref(false)

// заявки перечитали (сменили день, что-то удалили) — отметки на исчезнувших снимаем сами
watch(requests, () => selection.keepOnly(requests.value.map((request) => request.id)))

function plural(count, one, few, many) {
  const tens = count % 100
  const units = count % 10
  if (tens >= 11 && tens <= 14) return `${count} ${many}`
  if (units === 1) return `${count} ${one}`
  if (units >= 2 && units <= 4) return `${count} ${few}`
  return `${count} ${many}`
}

const selectedTitle = computed(() =>
  plural(selection.count.value, 'заявка', 'заявки', 'заявок'),
)

// групповая смена статуса возможна, когда у всех отмеченных статус один: переходы у
// разных статусов разные, и одним списком их не покажешь
const selectedStatusId = computed(() => {
  const statuses = new Set(
    requests.value.filter((request) => selection.isSelected(request.id)).map((request) => request.status_id),
  )
  return statuses.size === 1 ? [...statuses][0] : null
})

// групповая правка: сервер меняет либо все отмеченные заявки, либо ни одной
async function applyBulkEdit(fields) {
  const ids = selection.selectedIds.value
  const report = await runBulk(() => updateRequests(ids, fields))
  if (report === null) return
  bulkEditOpen.value = false
  selection.clear()
  await refreshDay()
  showNotice(`Изменено: ${plural(report.updated, 'заявка', 'заявки', 'заявок')}`)
}

// групповое удаление: что можно — удаляем, про остальное показываем причины
async function removeSelected() {
  const ids = selection.selectedIds.value
  if (!window.confirm(`Удалить ${plural(ids.length, 'заявку', 'заявки', 'заявок')}?`)) return
  const report = await runBulk(() => deleteRequests(ids))
  if (report === null) return
  selection.clear()
  await refreshDay()
  if (report.problems.length) {
    errorMessage.value = `Удалено: ${report.deleted}. Не удалось удалить: ${report.problems.length}`
    errorDetails.value = report.problems.map((problem) => problem.reason)
    return
  }
  showNotice(`Удалено: ${plural(report.deleted, 'заявка', 'заявки', 'заявок')}`)
}

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

const bulkSaving = ref(false)

// пришли из маршрута плана — показываем ту самую заявку; обратно — «Открыть в плане»
const { takeRequestId, openPlan } = usePlanFocus()

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

const { selectedDay, daysWithRequests, selectDay, refreshDaysWithRequests } = useSelectedDay()

// хвосты дней: «Новые» заявки с уже закрытым окном. Прошедший день не пересчитать — такие
// заявки иначе висят незамеченными; по клику — день и только просроченные
const overdueDays = computed(() => daysWithRequests.value.filter((day) => day.overdue_requests > 0))
const overdueTotal = computed(() => overdueDays.value.reduce((sum, day) => sum + day.overdue_requests, 0))

// перевели системные часы — просроченными стали другие заявки: перечитываем дни
const { offsetSeconds } = useSystemTime()
watch(offsetSeconds, () => refreshDaysWithRequests())

function showOverdue(day) {
  selectDay(day)
  filters.statusId = OVERDUE_FILTER
}

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
      <span>⚠ Пересчёт №{{ pendingReplan.id }} посчитан — он вступит в силу сам, в свой момент</span>
      <button type="button" class="link" @click="openPlan(pendingReplan.id)">
        Открыть пересчёт №{{ pendingReplan.id }} →
      </button>
    </p>
    <p v-else-if="needsReplan" class="replan-warning">
      <span>⚠ Рекомендуется пересчитать план</span>
      <button type="button" class="link" @click="openPlan(planSummary.id)">Открыть план №{{ planSummary.id }} →</button>
    </p>

    <!-- хвосты прошедших дней: списком по датам, по клику — день с фильтром «Просроченные» -->
    <section v-if="overdueDays.length" class="overdue-panel">
      <header>
        <strong>⚠ Просроченные заявки: {{ overdueTotal }}</strong>
        <span>окно закрылось, а заявка всё ещё «Новая» — перенесите или отмените</span>
      </header>
      <ul>
        <li v-for="day in overdueDays" :key="day.plan_date" :class="{ current: day.plan_date === selectedDay }">
          <span class="overdue-day">{{ formatDay(day.plan_date) }}</span>
          <span class="overdue-count">{{ plural(day.overdue_requests, 'заявка', 'заявки', 'заявок') }}</span>
          <button type="button" class="link" @click="showOverdue(day.plan_date)">показать →</button>
        </li>
      </ul>
    </section>

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
          :selected-ids="selection.selectedIds.value"
          :all-selected="selection.allVisibleSelected.value"
          :some-selected="selection.someVisibleSelected.value"
          @toggle-row="selection.toggleRow"
          @toggle-all="selection.toggleVisible"
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
          @reset-filters="resetEverything"
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

      <div v-else ref="mapArea" class="map-view" :style="{ '--details-width': detailsWidth }">
        <RequestsFilters
          @widths="filterWidths = $event"
          :filters="filters"
          :references="references"
          :active-count="activeFilterCount"
          :checked-count="selection.count.value"
          @reset="resetEverything"
        />

        <div class="map-area">
          <RequestsMap
            :requests="filteredRequests"
            :references="references"
            :selected-id="selectedId"
            :checked-ids="selection.selectedIds.value"
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

    <RequestsBulkEditDialog
      v-if="bulkEditOpen"
      :count="selection.count.value"
      :references="references"
      :saving="bulkSaving"
      :plan-date="selectedDay"
      :status-id="selectedStatusId"
      @apply="applyBulkEdit"
      @close="bulkEditOpen = false"
    />
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

/* просроченные заявки: заголовок и даты столбиком — у каждой ссылка на свой день */
.overdue-panel {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px 12px;
  border: 1px solid #fcd34d;
  border-radius: 8px;
  background: #fffbeb;
  color: #92400e;
  font-size: 13px;
}

.overdue-panel header {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 4px 10px;
}

.overdue-panel header span {
  color: #a16207;
  font-size: 12px;
}

.overdue-panel ul {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.overdue-panel li {
  display: grid;
  grid-template-columns: 96px 90px auto;
  align-items: baseline;
  padding-left: 18px;
}

.overdue-panel li.current .overdue-day {
  font-weight: 700;
}

.overdue-day {
  font-variant-numeric: tabular-nums;
}

.overdue-panel .link {
  justify-self: start;
  color: #b45309;
  font-weight: 600;
}
</style>
