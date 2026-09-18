<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'

import { NEW_ENGINEER } from '../composables/useEngineersTable.js'
import { useColumnWidths } from '../composables/useColumnWidths.js'
import { ENGINEER_COLUMNS as COLUMNS } from '../composables/useEngineersView.js'
import { referenceName } from '../utils/referenceNames.js'
import { transportColor } from '../utils/transportColors.js'
import IconButton from './IconButton.vue'
import StartPointIcon from './StartPointIcon.vue'
import TimeRangeValue from './TimeRangeValue.vue'
import EngineerEditCells from './EngineerEditCells.vue'
import EngineersFilterControl from './EngineersFilterControl.vue'

const props = defineProps({
  engineers: { type: Array, required: true }, // уже отфильтрованные и отсортированные
  references: { type: Object, required: true },
  editingId: { type: [Number, String], default: null },
  form: { type: Object, default: null },
  saving: { type: Boolean, required: true },
  sortKey: { type: String, required: true },
  sortDirection: { type: String, required: true },
  selectedId: { type: Number, default: null },
  emptyText: { type: String, default: 'Исполнителей нет' },
  filters: { type: Object, required: true },
  activeFilterCount: { type: Number, required: true },
})
defineEmits(['edit', 'cancel', 'save', 'remove', 'sort', 'select', 'reset-filters', 'show-on-map'])

// старты остальных бригад — ориентир на карте выбора координаты
const contextPoints = computed(() =>
  props.engineers
    .filter((engineer) => engineer.id !== props.editingId)
    .map((engineer) => ({
      latitude: engineer.start_latitude,
      longitude: engineer.start_longitude,
      label: engineer.name,
    })),
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

// исполнителя выбрали на карте — прокручиваем таблицу к его строке
const tableRoot = ref(null)
// ширины колонок — от ширины таблицы: компактные своей ширины, остальное — растущим
const { widths } = useColumnWidths(COLUMNS, tableRoot)

async function scrollToSelected() {
  if (props.selectedId === null) return
  await nextTick()
  tableRoot.value
    ?.querySelector(`[data-engineer-id="${props.selectedId}"]`)
    ?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
}

watch(() => props.selectedId, scrollToSelected)
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
            <EngineersFilterControl
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
        <tr v-if="editingId === NEW_ENGINEER" class="editing">
          <td>
            <input v-model="form.id" type="number" min="1" class="short-input" placeholder="авто" />
          </td>
          <EngineerEditCells
            :form="form"
            :references="references"
            :saving="saving"
            :context-points="contextPoints"
            @save="$emit('save')"
            @cancel="$emit('cancel')"
          />
        </tr>

        <tr
          v-for="engineer in engineers"
          :key="engineer.id"
          :data-engineer-id="engineer.id"
          :class="{ editing: engineer.id === editingId, selected: engineer.id === selectedId }"
          @click="editingId === null && $emit('select', engineer.id)"
          @dblclick="editingId === null && $emit('show-on-map', engineer.id)"
        >
          <td class="number-cell">{{ engineer.id }}</td>

          <EngineerEditCells
            v-if="engineer.id === editingId"
            :form="form"
            :references="references"
            :saving="saving"
            :context-points="contextPoints"
            @save="$emit('save')"
            @cancel="$emit('cancel')"
          />

          <template v-else>
            <td class="wide-cell">{{ engineer.name }}</td>
            <td class="nowrap">
              <i class="legend-dot" :style="{ background: transportColor(engineer.transport_id) }"></i>
              {{ referenceName(references, 'transports', engineer.transport_id) }}
            </td>
            <td>
              <div class="chips">
                <span v-for="skillId in engineer.skill_ids" :key="skillId" class="badge">
                  {{ referenceName(references, 'skills', skillId) }}
                </span>
              </div>
            </td>
            <td class="range-cell">
              <TimeRangeValue :start="engineer.shift_start" :end="engineer.shift_end" />
            </td>
            <td
              class="start-cell"
              :title="
                engineer.start_at_office
                  ? `Из офиса «${referenceName(references, 'offices', engineer.office_id)}»`
                  : `Своя точка: ${engineer.start_latitude.toFixed(4)}, ${engineer.start_longitude.toFixed(4)}`
              "
            >
              <StartPointIcon :at-office="engineer.start_at_office" />
            </td>
            <td>
              <div class="row-actions" @dblclick.stop>
                <IconButton
                  icon="edit"
                  label="Изменить"
                  :disabled="editingId !== null"
                  @click.stop="$emit('edit', engineer)"
                />
                <IconButton
                  icon="delete"
                  label="Удалить"
                  variant="danger"
                  :disabled="editingId !== null"
                  @click.stop="$emit('remove', engineer)"
                />
              </div>
            </td>
          </template>
        </tr>

        <tr v-if="engineers.length === 0 && editingId !== NEW_ENGINEER">
          <td :colspan="COLUMNS.length" class="empty">{{ emptyText }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

