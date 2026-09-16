<script setup>
// Ячейки строки таблицы исполнителей в режиме редактирования (всё, кроме номера).
// form — объект формы из useEngineersTable, поля ввода меняют его напрямую.
import DayTimeRange from './DayTimeRange.vue'
import IconButton from './IconButton.vue'
import PointPickerButton from './PointPickerButton.vue'

const props = defineProps({
  form: { type: Object, required: true },
  references: { type: Object, required: true },
  saving: { type: Boolean, required: true },
  // старты других бригад — ориентир на карте выбора
  contextPoints: { type: Array, default: () => [] },
})
const emit = defineEmits(['save', 'cancel'])

function applyPickedPoint(latitude, longitude) {
  props.form.start_latitude = latitude
  props.form.start_longitude = longitude
}
</script>

<template>
  <td>
    <input v-model="form.name" class="wide-input" placeholder="Бригада …" />
  </td>
  <td>
    <select v-model="form.transport_id">
      <option v-for="item in references.transports" :key="item.id" :value="item.id">{{ item.name }}</option>
    </select>
  </td>
  <td>
    <div class="skill-checkboxes" title="От 1 до 3 навыков">
      <label v-for="skill in references.skills" :key="skill.id">
        <input v-model="form.skill_ids" type="checkbox" :value="skill.id" />
        {{ skill.name }}
      </label>
    </div>
  </td>
  <td>
    <DayTimeRange v-model:start="form.shift_start" v-model:end="form.shift_end" />
  </td>
  <td>
    <div class="coordinates-cell">
      <div class="coordinate-inputs">
        <input v-model="form.start_latitude" type="number" step="any" placeholder="широта" />
        <input v-model="form.start_longitude" type="number" step="any" placeholder="долгота" />
      </div>
      <PointPickerButton
        title="Откуда выезжает бригада"
        hint="Указать координаты на карте"
        :latitude="form.start_latitude"
        :longitude="form.start_longitude"
        :context-points="contextPoints"
        @pick="applyPickedPoint"
      />
    </div>
  </td>
  <td>
    <div class="row-actions">
      <IconButton
        icon="save"
        :label="saving ? 'Сохраняю…' : 'Сохранить'"
        variant="primary"
        :disabled="saving"
        @click="emit('save')"
      />
      <IconButton icon="cancel" label="Отмена" :disabled="saving" @click="emit('cancel')" />
    </div>
  </td>
</template>

<style scoped>
.skill-checkboxes {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.coordinates-cell {
  display: flex;
  align-items: center;
  gap: 6px;
}

.coordinate-inputs {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.skill-checkboxes label {
  display: flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
}

.skill-checkboxes input {
  width: 16px;
  min-width: 0;
  height: 16px;
  padding: 0;
}
</style>
