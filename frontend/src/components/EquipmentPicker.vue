<script setup>
// Выбор оборудования с количеством — для заявки и для бригады.
// Два шага: кнопка открывает список с галочками, отмеченный тип появляется под кнопкой
// с количеством 1 — его можно поменять. Список открывается поверх страницы (Teleport):
// ячейка таблицы его не обрезает и не раздвигается под него, сколько бы типов ни было.
import { computed, nextTick, onBeforeUnmount, ref } from 'vue'

const props = defineProps({
  modelValue: { type: Object, required: true }, // { номер оборудования: количество }
  options: { type: Array, required: true }, // справочник оборудования
  emptyLabel: { type: String, default: 'не выбрано' },
})
const emit = defineEmits(['update:modelValue'])

const open = ref(false)
const trigger = ref(null)
const panel = ref(null)
const position = ref({ top: 0, left: 0, minWidth: 0 })

const selected = computed(() => props.options.filter((item) => item.id in props.modelValue))
const summary = computed(() => (selected.value.length ? `выбрано: ${selected.value.length}` : props.emptyLabel))

// отметили — одна штука, сняли галочку — тип уходит вместе с количеством
function toggle(equipmentId) {
  const next = { ...props.modelValue }
  if (equipmentId in next) delete next[equipmentId]
  else next[equipmentId] = 1
  emit('update:modelValue', next)
}

// пока количество набирается, поле может быть пустым — число подставится при сохранении
function setQuantity(equipmentId, value) {
  emit('update:modelValue', { ...props.modelValue, [equipmentId]: value === '' ? '' : Number(value) })
}

function onOutsideClick(event) {
  if (panel.value?.contains(event.target) || trigger.value?.contains(event.target)) return
  close()
}

async function openPanel() {
  const box = trigger.value.getBoundingClientRect()
  position.value = { top: box.bottom + 2, left: box.left, minWidth: Math.max(box.width, 200) }
  open.value = true
  await nextTick()
  document.addEventListener('mousedown', onOutsideClick, true)
  // страница прокрутилась — список остался бы висеть не у кнопки
  window.addEventListener('scroll', close, true)
  window.addEventListener('resize', close)
}

function close() {
  open.value = false
  document.removeEventListener('mousedown', onOutsideClick, true)
  window.removeEventListener('scroll', close, true)
  window.removeEventListener('resize', close)
}

onBeforeUnmount(close)
</script>

<template>
  <div class="equipment-picker" @keydown.esc="close">
    <button
      ref="trigger"
      type="button"
      class="picker-trigger"
      :aria-expanded="open"
      aria-haspopup="listbox"
      @click="open ? close() : openPanel()"
    >
      <span class="picker-summary">{{ summary }}</span>
      <span class="picker-arrow" aria-hidden="true">▾</span>
    </button>

    <div v-for="item in selected" :key="item.id" class="picker-row">
      <input
        type="number"
        min="1"
        max="999"
        :value="modelValue[item.id]"
        :aria-label="`${item.name}, штук`"
        @input="setQuantity(item.id, $event.target.value)"
      />
      <span class="picker-name" :title="item.name">{{ item.name }}</span>
    </div>

    <Teleport to="body">
      <div
        v-if="open"
        ref="panel"
        class="picker-panel"
        role="listbox"
        aria-multiselectable="true"
        :style="{ top: `${position.top}px`, left: `${position.left}px`, minWidth: `${position.minWidth}px` }"
        @keydown.esc="close"
      >
        <label v-for="item in options" :key="item.id" class="picker-option" :title="item.description">
          <input type="checkbox" :checked="item.id in modelValue" @change="toggle(item.id)" />
          <span>{{ item.name }}</span>
        </label>
        <p v-if="!options.length" class="picker-empty">Справочник оборудования пуст</p>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.equipment-picker {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

/* кнопка выглядит как выпадающий список строки правки: та же высота, рамка и шрифт */
.picker-trigger {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  width: 100%;
  min-width: 0;
  height: 24px;
  padding: 2px 6px;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  background: #fff;
  color: #0f172a;
  font-size: 12px;
  text-align: left;
}

.picker-trigger[aria-expanded='true'] {
  border-color: #2563eb;
  box-shadow: 0 0 0 2px rgb(37 99 235 / 15%);
}

.picker-summary {
  overflow: hidden;
  text-overflow: ellipsis;
}

.picker-arrow {
  flex-shrink: 0;
  color: #64748b;
  font-size: 10px;
}

.picker-row {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  font-size: 12px;
}

/* поле количества узкое: общее правило строки правки растянуло бы его на всю ячейку */
.picker-row input,
.data-table.fixed-columns tbody tr.editing .picker-row input {
  flex-shrink: 0;
  width: 48px;
  height: 22px;
  padding: 1px 4px;
  font-size: 12px;
  text-align: right;
}

.picker-name {
  min-width: 0;
  overflow-wrap: anywhere;
}

/* список поверх страницы — рядом с кнопкой, под ней */
.picker-panel {
  position: fixed;
  z-index: 1500;
  display: flex;
  flex-direction: column;
  gap: 2px;
  max-height: 260px;
  padding: 4px;
  overflow: auto;
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  background: #fff;
  box-shadow: 0 8px 24px rgb(15 23 42 / 16%);
  font-size: 13px;
}

.picker-option {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 8px;
  border-radius: 6px;
  cursor: pointer;
}

.picker-option:hover {
  background: #eff6ff;
}

.picker-option input {
  width: 14px;
  height: 14px;
  margin: 0;
}

.picker-empty {
  margin: 0;
  padding: 6px 8px;
  color: #64748b;
}
</style>
