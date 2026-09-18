<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'

import { NEW_REQUEST } from '../composables/useRequestsTable.js'
import { useColumnWidths } from '../composables/useColumnWidths.js'
import { REQUEST_COLUMNS as COLUMNS } from '../composables/useRequestsView.js'
import { isUrgent, referenceName } from '../utils/referenceNames.js'
import IconButton from './IconButton.vue'
import TimeRangeValue from './TimeRangeValue.vue'
import RequestEditCells from './RequestEditCells.vue'
import RequestsFilterControl from './RequestsFilterControl.vue'

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
// ширины колонок — от ширины таблицы: компактные своей ширины, остальное — растущим
const { widths } = useColumnWidths(COLUMNS, tableRoot)

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
    <table class="data-table fixed-columns fluid">
      <colgroup>
        <col v-for="column in COLUMNS" :key="column.key" :style="{ width: `${widths[column.key]}px` }" />
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
        <tr class="filter-row filter-controls">
          <th v-for="column in COLUMNS" :key="column.key" :class="{ 'actions-cell': column.key === 'actions' }">
            <RequestsFilterControl
              :column="column.key"
              :filters="filters"
              :references="references"
              :active-filter-count="activeFilterCount"
              @reset="$emit('reset-filters')"
            />
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
            <!-- на узком экране координаты уходят в две строки по запятой, а не обрезаются -->
            <td class="coordinates-value">{{ request.latitude.toFixed(4) }}, {{ request.longitude.toFixed(4) }}</td>
            <td>
              {{ referenceName(references, 'work_types', request.work_type_id) }}
              <!-- требуемое оборудование — под названием, каждое своей строкой -->
              <span
                v-for="equipmentId in request.equipment_ids ?? []"
                :key="equipmentId"
                class="equipment-badge"
                title="Что техник должен привезти на заявку"
              >
                ⚙ {{ referenceName(references, 'equipment', equipmentId) }}
              </span>
            </td>
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

<style scoped>
.coordinates-value {
  font-variant-numeric: tabular-nums;
}

/* требуемое оборудование: каждое отдельной строкой под типом работ, мелко и заметно */
.equipment-badge {
  display: table;
  margin-top: 4px;
  padding: 0 6px;
  border-radius: 999px;
  background: #fef3c7;
  color: #92400e;
  font-size: 12px;
  line-height: 18px;
  white-space: nowrap;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  vertical-align: top;
}
</style>
