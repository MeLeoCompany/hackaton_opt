<script setup>
import { nextTick, onMounted, ref, watch } from 'vue'

import { NEW_ENGINEER } from '../composables/useEngineersTable.js'
import { formatMoscowWindow } from '../utils/moscowTime.js'
import { referenceName } from '../utils/referenceNames.js'
import { transportColor } from '../utils/transportColors.js'
import EngineerEditCells from './EngineerEditCells.vue'

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
})
defineEmits(['edit', 'cancel', 'save', 'remove', 'sort', 'select'])

// sortKey: null — по колонке не сортируем
const COLUMNS = [
  { label: '№', sortKey: 'id' },
  { label: 'Имя', sortKey: 'name' },
  { label: 'Транспорт', sortKey: 'transport' },
  { label: 'Навыки', sortKey: 'skills' },
  { label: 'Смена (МСК)', sortKey: 'shift_start' },
  { label: 'Старт', sortKey: null },
  { label: '', sortKey: null },
]

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
    <table class="data-table">
      <thead>
        <tr>
          <th
            v-for="(column, columnIndex) in COLUMNS"
            :key="columnIndex"
            :class="{ sortable: column.sortKey, sorted: column.sortKey && column.sortKey === sortKey }"
            :aria-sort="ariaSort(column.sortKey)"
            @click="column.sortKey && $emit('sort', column.sortKey)"
          >
            {{ column.label }}
            <span v-if="column.sortKey" class="sort-arrow">{{ sortArrow(column.sortKey) }}</span>
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
        >
          <td class="number-cell">{{ engineer.id }}</td>

          <EngineerEditCells
            v-if="engineer.id === editingId"
            :form="form"
            :references="references"
            :saving="saving"
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
            <td class="nowrap">{{ formatMoscowWindow(engineer.shift_start, engineer.shift_end) }}</td>
            <td class="number-cell">
              {{ engineer.start_latitude.toFixed(4) }}, {{ engineer.start_longitude.toFixed(4) }}
            </td>
            <td>
              <div class="row-actions">
                <button :disabled="editingId !== null" @click.stop="$emit('edit', engineer)">Изменить</button>
                <button class="danger" :disabled="editingId !== null" @click.stop="$emit('remove', engineer)">
                  Удалить
                </button>
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
