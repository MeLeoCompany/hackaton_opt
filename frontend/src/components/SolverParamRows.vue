<script setup>
// Строки параметров решателя — одни и те же в «Системе» и в диалоге расчёта: параметр,
// значение и карандаш справа. Карандаш превращает значение в поле прямо в строке.
// Что делать с новым значением, решает хозяин таблицы: «Система» сохраняет его на сервер,
// диалог — только для этого расчёта.
import { ref } from 'vue'

import IconButton from './IconButton.vue'
import InfoHint from './InfoHint.vue'
import { SOLVER_ROWS, paramText } from '../utils/solverParams.js'

const props = defineProps({
  values: { type: Object, required: true },
  // с чем сравнивать: в диалоге — системные значения, чтобы было видно, что поменяли
  baseline: { type: Object, default: null },
  disabled: { type: Boolean, default: false },
  // строки лежат внутри группы — их текст начинается под названием группы
  indent: { type: Boolean, default: false },
})
const emit = defineEmits(['update'])

const editingKey = ref(null)
const editValue = ref('')

function startEdit(key) {
  editingKey.value = key
  editValue.value = props.values[key]
}

function apply(key) {
  emit('update', key, editValue.value)
  editingKey.value = null
}

function changed(key) {
  return props.baseline !== null && `${props.baseline[key]}` !== `${props.values[key]}`
}
</script>

<template>
  <tr v-for="field in SOLVER_ROWS" :key="field.key" :class="['param-row', { changed: changed(field.key) }]">
    <td :class="{ 'child-name': indent }">{{ field.label }} <InfoHint :text="field.hint" /></td>
    <td class="value">
      <template v-if="editingKey === field.key">
        <select
          v-if="field.key === 'verbose_log'"
          v-model="editValue"
          class="value-input"
          :disabled="disabled"
          aria-label="подробный лог решателя"
        >
          <option :value="false">выключен</option>
          <option :value="true">включён</option>
        </select>
        <input
          v-else
          v-model="editValue"
          type="number"
          :step="field.step"
          :min="field.min"
          class="value-input"
          :disabled="disabled"
          :aria-label="field.label"
          @keyup.enter="apply(field.key)"
          @keyup.esc="editingKey = null"
        />
      </template>
      <template v-else>
        {{ paramText(field.key, values[field.key]) }}
        <span v-if="changed(field.key)" class="was">системное {{ paramText(field.key, baseline[field.key]) }}</span>
      </template>
    </td>
    <td>
      <div class="row-actions">
        <template v-if="editingKey === field.key">
          <IconButton icon="save" label="Применить" variant="primary" :disabled="disabled" @click="apply(field.key)" />
          <IconButton icon="cancel" label="Отменить" :disabled="disabled" @click="editingKey = null" />
        </template>
        <IconButton
          v-else
          icon="edit"
          label="Изменить"
          :disabled="disabled || editingKey !== null"
          @click="startEdit(field.key)"
        />
      </div>
    </td>
  </tr>
</template>

<style scoped>
.value {
  color: #334155;
  font-family: ui-monospace, monospace;
  font-size: 12px;
}

/* поле не шире колонки значения: в диалоге она узкая */
.value-input {
  width: 100%;
  max-width: 160px;
}

/* параметр поменяли на этот расчёт: видно и новое значение, и системное */
.changed .value {
  color: #1d4ed8;
  font-weight: 600;
}

.was {
  margin-left: 8px;
  color: #94a3b8;
  font-family: inherit;
  font-weight: 400;
}

/* текст строк группы начинается ровно под её названием; селектор длиннее,
   потому что общий стиль ячеек таблицы сильнее */
.data-table tbody td.child-name {
  padding-left: 27px;
}

.param-row td {
  background: #fbfdff;
}

/* кнопки строки — как во всех таблицах приложения: делят ячейку поровну. В «Системе» это
   даёт fixed-columns, в диалоге таблица обычная — повторяем то же правило */
.param-row .row-actions {
  display: flex;
  gap: 6px;
}

.param-row .row-actions :deep(.icon-button) {
  flex: 1;
  width: auto;
}
</style>
