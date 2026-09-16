<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'

import { NEW_REQUEST } from '../composables/useRequestsTable.js'
import { NO_TRANSPORT } from '../composables/useRequestsView.js'
import { isUrgent, referenceName } from '../utils/referenceNames.js'
import IconButton from './IconButton.vue'
import TimeRangeValue from './TimeRangeValue.vue'
import RequestEditCells from './RequestEditCells.vue'
import TimeInput from './TimeInput.vue'

const props = defineProps({
  requests: { type: Array, required: true }, // заявки текущей страницы, уже отсортированные
  references: { type: Object, required: true },
  editingId: { type: [Number, String], default: null },
  form: { type: Object, default: null },
  saving: { type: Boolean, required: true },
  sortKey: { type: String, required: true },
  sortDirection: { type: String, required: true },
  selectedId: { type: Number, default: null },
  emptyText: { type: String, default: 'Заявок нет' },
  filters: { type: Object, required: true },
  activeFilterCount: { type: Number, required: true },
})
defineEmits([
  'edit',
  'cancel',
  'save',
  'remove',
  'sort',
  'select',
  'toggle-active',
  'work-type-picked',
  'reset-filters',
  'show-on-map',
])

// sortKey: null — по колонке не сортируем; key — какой фильтр стоит под колонкой;
// width — фиксированная ширина, чтобы колонки не прыгали при фильтрации и правке строки
const COLUMNS = [
  { key: 'id', label: '№', sortKey: 'id', width: '90px' },
  { key: 'is_active', label: 'Активна', sortKey: 'is_active', width: '110px' },
  { key: 'address', label: 'Адрес', sortKey: 'address', width: '' },
  { key: 'coordinates', label: 'Координаты', sortKey: null, width: '150px' },
  { key: 'work_type', label: 'Тип работ', sortKey: 'work_type', width: '320px' },
  { key: 'duration', label: 'Работа, мин', sortKey: 'duration_minutes', width: '110px' },
  { key: 'window', label: 'Окно (МСК)', sortKey: 'window_start', width: '130px' },
  { key: 'priority', label: 'Приоритет', sortKey: 'priority', width: '130px' },
  { key: 'transport', label: 'Транспорт', sortKey: 'transport', width: '150px' },
  { key: 'actions', label: '', sortKey: null, width: '130px' },
]

// точки остальных заявок страницы — ориентир на карте выбора координаты
const contextPoints = computed(() =>
  props.requests
    .filter((request) => request.id !== props.editingId)
    .map((request) => ({ latitude: request.latitude, longitude: request.longitude, label: request.address })),
)

function sortArrow(columnSortKey) {
  if (props.sortKey !== columnSortKey) return '↕'
  return props.sortDirection === 'asc' ? '↑' : '↓'
}

function ariaSort(columnSortKey) {
  if (!columnSortKey) return undefined
  if (props.sortKey !== columnSortKey) return 'none'
  return props.sortDirection === 'asc' ? 'ascending' : 'descending'
}

// заявку выбрали на карте — прокручиваем таблицу к её строке
const tableRoot = ref(null)

async function scrollToSelected() {
  if (props.selectedId === null) return
  await nextTick()
  tableRoot.value
    ?.querySelector(`[data-request-id="${props.selectedId}"]`)
    ?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
}

watch(() => props.selectedId, scrollToSelected)
// таблица появляется заново после «Показать в таблице» на карте
onMounted(scrollToSelected)
</script>

<template>
  <div ref="tableRoot" class="table-scroll">
    <table class="data-table fixed-columns">
      <colgroup>
        <col v-for="column in COLUMNS" :key="column.key" :style="column.width ? { width: column.width } : null" />
      </colgroup>
      <thead>
        <tr>
          <th
            v-for="column in COLUMNS"
            :key="column.key"
            :class="{ sortable: column.sortKey, sorted: column.sortKey && column.sortKey === sortKey }"
            :aria-sort="ariaSort(column.sortKey)"
            @click="column.sortKey && $emit('sort', column.sortKey)"
          >
            {{ column.label }}
            <span v-if="column.sortKey" class="sort-arrow">{{ sortArrow(column.sortKey) }}</span>
          </th>
        </tr>

        <!-- отдельная строка фильтров под названиями колонок -->
        <tr class="filter-row">
          <th v-for="column in COLUMNS" :key="column.key" :class="{ 'actions-cell': column.key === 'actions' }">
            <input
              v-if="column.key === 'id'"
              v-model="filters.idText"
              inputmode="numeric"
              placeholder="номер"
              aria-label="фильтр по номеру заявки"
            />

            <select v-else-if="column.key === 'is_active'" v-model="filters.activity" aria-label="фильтр по планированию">
              <option value="">все</option>
              <option value="active">активные</option>
              <option value="inactive">выключенные</option>
            </select>

            <input
              v-else-if="column.key === 'address'"
              v-model="filters.text"
              placeholder="адрес"
              aria-label="фильтр по адресу"
            />

            <input
              v-else-if="column.key === 'coordinates'"
              v-model="filters.coordinates"
              placeholder="55.74"
              aria-label="фильтр по координатам"
            />

            <select v-else-if="column.key === 'work_type'" v-model="filters.workTypeId" aria-label="фильтр по типу работ">
              <option value="">любой</option>
              <option v-for="item in references.work_types" :key="item.id" :value="item.id">{{ item.name }}</option>
            </select>

            <div v-else-if="column.key === 'duration'" class="range-pair">
              <input
                v-model="filters.durationFrom"
                type="number"
                min="0"
                placeholder="от"
                aria-label="работа на месте не меньше"
              />
              <span>–</span>
              <input
                v-model="filters.durationTo"
                type="number"
                min="0"
                placeholder="до"
                aria-label="работа на месте не больше"
              />
            </div>

            <div v-else-if="column.key === 'window'" class="time-range">
              <TimeInput v-model="filters.timeFrom" aria-label="окно начинается не раньше" />
              <span>–</span>
              <TimeInput v-model="filters.timeTo" aria-label="окно начинается не позже" />
            </div>

            <select v-else-if="column.key === 'priority'" v-model="filters.priorityId" aria-label="фильтр по приоритету">
              <option value="">любой</option>
              <option v-for="item in references.priorities" :key="item.id" :value="item.id">{{ item.name }}</option>
            </select>

            <select v-else-if="column.key === 'transport'" v-model="filters.transportId" aria-label="фильтр по транспорту">
              <option value="">любой</option>
              <option :value="NO_TRANSPORT">не важен</option>
              <option v-for="item in references.transports" :key="item.id" :value="item.id">{{ item.name }}</option>
            </select>

            <button
              v-else-if="column.key === 'actions'"
              class="link"
              :disabled="activeFilterCount === 0"
              @click="$emit('reset-filters')"
            >
              Сбросить{{ activeFilterCount ? ` (${activeFilterCount})` : '' }}
            </button>
          </th>
        </tr>
      </thead>
      <tbody>
        <tr v-if="editingId === NEW_REQUEST" class="editing">
          <td>
            <input v-model="form.id" type="number" min="1" class="short-input" placeholder="авто" />
          </td>
          <RequestEditCells
            :form="form"
            :references="references"
            :saving="saving"
            :context-points="contextPoints"
            @save="$emit('save')"
            @cancel="$emit('cancel')"
            @work-type-picked="$emit('work-type-picked', $event)"
          />
        </tr>

        <tr
          v-for="request in requests"
          :key="request.id"
          :data-request-id="request.id"
          :class="{
            editing: request.id === editingId,
            selected: request.id === selectedId,
            inactive: !request.is_active,
          }"
          @click="editingId === null && $emit('select', request.id)"
          @dblclick="editingId === null && $emit('show-on-map', request.id)"
        >
          <td class="number-cell">{{ request.id }}</td>

          <RequestEditCells
            v-if="request.id === editingId"
            :form="form"
            :references="references"
            :saving="saving"
            :context-points="contextPoints"
            @save="$emit('save')"
            @cancel="$emit('cancel')"
            @work-type-picked="$emit('work-type-picked', $event)"
          />

          <template v-else>
            <td>
              <label
                class="switch"
                :title="request.is_active ? 'Учитывается при планировании' : 'Не учитывается при планировании'"
                @click.stop
                @dblclick.stop
              >
                <input
                  type="checkbox"
                  :checked="request.is_active"
                  :disabled="editingId !== null"
                  @change="$emit('toggle-active', request)"
                />
                <span class="slider"></span>
              </label>
            </td>
            <td class="wide-cell">{{ request.address }}</td>
            <td class="number-cell nowrap">{{ request.latitude.toFixed(4) }}, {{ request.longitude.toFixed(4) }}</td>
            <td>{{ referenceName(references, 'work_types', request.work_type_id) }}</td>
            <td class="number-cell under-range-filter">{{ request.duration_minutes }}</td>
            <td class="range-cell">
              <TimeRangeValue :start="request.window_start" :end="request.window_end" />
            </td>
            <td>
              <span :class="['badge', { urgent: isUrgent(references, request) }]">
                {{ referenceName(references, 'priorities', request.priority_id) }}
              </span>
            </td>
            <td>{{ referenceName(references, 'transports', request.transport_id) }}</td>
            <td>
              <div class="row-actions" @dblclick.stop>
                <IconButton
                  icon="edit"
                  label="Изменить"
                  :disabled="editingId !== null"
                  @click.stop="$emit('edit', request)"
                />
                <IconButton
                  icon="delete"
                  label="Удалить"
                  variant="danger"
                  :disabled="editingId !== null"
                  @click.stop="$emit('remove', request)"
                />
              </div>
            </td>
          </template>
        </tr>

        <tr v-if="requests.length === 0 && editingId !== NEW_REQUEST">
          <td :colspan="COLUMNS.length" class="empty">{{ emptyText }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
