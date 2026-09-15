<script setup>
import { nextTick, onMounted, ref, watch } from 'vue'

import { NEW_REQUEST } from '../composables/useRequestsTable.js'
import { formatMoscowWindow } from '../utils/moscowTime.js'
import { isUrgent, referenceName } from '../utils/referenceNames.js'
import RequestEditCells from './RequestEditCells.vue'

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
})
defineEmits(['edit', 'cancel', 'save', 'remove', 'sort', 'select', 'toggle-active'])

// sortKey: null — по колонке не сортируем
const COLUMNS = [
  { label: '№', sortKey: 'id' },
  { label: 'Активна', sortKey: 'is_active' },
  { label: 'Адрес', sortKey: 'address' },
  { label: 'Широта', sortKey: null },
  { label: 'Долгота', sortKey: null },
  { label: 'Работа, мин', sortKey: 'duration_minutes' },
  { label: 'Окно (МСК)', sortKey: 'window_start' },
  { label: 'Приоритет', sortKey: 'priority' },
  { label: 'Навык', sortKey: 'skill' },
  { label: 'Транспорт', sortKey: 'transport' },
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
    <table class="requests-table">
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
        <tr v-if="editingId === NEW_REQUEST" class="editing">
          <td>
            <input v-model="form.id" type="number" min="1" class="id-input" placeholder="авто" />
          </td>
          <RequestEditCells
            :form="form"
            :references="references"
            :saving="saving"
            @save="$emit('save')"
            @cancel="$emit('cancel')"
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
        >
          <td class="number-cell">{{ request.id }}</td>

          <RequestEditCells
            v-if="request.id === editingId"
            :form="form"
            :references="references"
            :saving="saving"
            @save="$emit('save')"
            @cancel="$emit('cancel')"
          />

          <template v-else>
            <td>
              <label
                class="switch"
                :title="request.is_active ? 'Учитывается при планировании' : 'Не учитывается при планировании'"
                @click.stop
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
            <td class="address">{{ request.address }}</td>
            <td class="number-cell">{{ request.latitude.toFixed(4) }}</td>
            <td class="number-cell">{{ request.longitude.toFixed(4) }}</td>
            <td class="number-cell">{{ request.duration_minutes }}</td>
            <td class="window">{{ formatMoscowWindow(request.window_start, request.window_end) }}</td>
            <td>
              <span :class="['badge', { urgent: isUrgent(references, request) }]">
                {{ referenceName(references, 'priorities', request.priority_id) }}
              </span>
            </td>
            <td>{{ referenceName(references, 'skills', request.skill_id) }}</td>
            <td>{{ referenceName(references, 'transports', request.transport_id) }}</td>
            <td>
              <div class="row-actions">
                <button :disabled="editingId !== null" @click.stop="$emit('edit', request)">Изменить</button>
                <button class="danger" :disabled="editingId !== null" @click.stop="$emit('remove', request)">
                  Удалить
                </button>
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
.table-scroll {
  overflow: auto;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
}

.requests-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

th {
  position: sticky;
  top: 0;
  z-index: 1;
  background: #f8fafc;
  text-align: left;
  font-weight: 600;
  color: #475569;
  padding: 8px 10px;
  border-bottom: 1px solid #e2e8f0;
  white-space: nowrap;
  user-select: none;
}

th.sortable {
  cursor: pointer;
}

th.sortable:hover,
th.sorted {
  color: #1d4ed8;
}

.sort-arrow {
  margin-left: 3px;
  font-size: 11px;
  opacity: 0.45;
}

th.sorted .sort-arrow {
  opacity: 1;
}

/* :deep — чтобы правила действовали и на ячейки из RequestEditCells */
.requests-table :deep(td) {
  padding: 7px 10px;
  border-bottom: 1px solid #f1f5f9;
  vertical-align: middle;
}

.requests-table tbody tr:not(.editing) {
  cursor: pointer;
}

.requests-table :deep(tbody tr:not(.editing):hover td) {
  background: #f8fafc;
}

/* выключенная заявка — приглушённая, но читаемая */
.requests-table :deep(tr.inactive td) {
  color: #94a3b8;
}

.requests-table :deep(tr.selected td) {
  background: #fef9c3;
}

.requests-table :deep(tr.editing td) {
  background: #eff6ff;
  color: inherit;
}

.number-cell {
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.address {
  min-width: 220px;
}

.window {
  white-space: nowrap;
}

.badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 10px;
  background: #f1f5f9;
  color: #334155;
  white-space: nowrap;
}

.badge.urgent {
  background: #fee2e2;
  color: #b91c1c;
}

tr.inactive .badge {
  opacity: 0.55;
}

/* переключатель активности */
.switch {
  position: relative;
  display: inline-block;
  width: 34px;
  height: 18px;
  vertical-align: middle;
}

.switch input {
  position: absolute;
  opacity: 0;
  width: 0;
  height: 0;
}

.slider {
  position: absolute;
  inset: 0;
  border-radius: 9px;
  background: #cbd5e1;
  cursor: pointer;
  transition: background 0.15s;
}

.slider::before {
  content: '';
  position: absolute;
  left: 2px;
  top: 2px;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: #fff;
  transition: transform 0.15s;
}

.switch input:checked + .slider {
  background: #16a34a;
}

.switch input:checked + .slider::before {
  transform: translateX(16px);
}

.switch input:disabled + .slider {
  opacity: 0.5;
  cursor: not-allowed;
}

.switch input:focus-visible + .slider {
  outline: 2px solid #2563eb;
  outline-offset: 2px;
}

.id-input {
  width: 80px;
}

.empty {
  text-align: center;
  color: #94a3b8;
  padding: 24px;
}
</style>
